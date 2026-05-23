/*
 * Driver xAI C driver for Waveshare 1.54 inch 200x200 black/white e-paper.
 *
 * The driver is framebuffer-free. Callers provide platform callbacks for
 * GPIO, SPI byte write, delay, and BUSY reads. Pixel value 1 means black,
 * and the panel byte stream uses 1 bits for white, 0 bits for black.
 */

#include <stdint.h>
#include <stddef.h>

#define EPAPER_1IN54_WIDTH 200u
#define EPAPER_1IN54_HEIGHT 200u
#define EPAPER_1IN54_BYTES_PER_ROW (EPAPER_1IN54_WIDTH / 8u)

typedef void (*epaper_1in54_write_pin_fn)(uint8_t value, void *user);
typedef uint8_t (*epaper_1in54_read_pin_fn)(void *user);
typedef void (*epaper_1in54_spi_write_fn)(uint8_t value, void *user);
typedef void (*epaper_1in54_delay_ms_fn)(uint32_t ms, void *user);

typedef struct {
    epaper_1in54_spi_write_fn spi_write;
    epaper_1in54_write_pin_fn cs_write;
    epaper_1in54_write_pin_fn dc_write;
    epaper_1in54_write_pin_fn rst_write;
    epaper_1in54_read_pin_fn busy_read;
    epaper_1in54_delay_ms_fn delay_ms;
    void *user;
    uint8_t busy_active_high;
} epaper_1in54_t;

typedef uint8_t (*epaper_1in54_pixel_fn)(uint16_t x, uint16_t y, void *user);

typedef struct {
    uint16_t width;
    uint16_t height;
    uint16_t bytes_per_row;
    uint8_t framebuffer_required;
} epaper_1in54_info_t;

static uint32_t epaper_abs_delta(uint32_t a, uint32_t b) {
    return a > b ? a - b : b - a;
}

static uint8_t epaper_in_ring(uint32_t x, uint32_t y, uint32_t cx, uint32_t cy, uint32_t radius, uint32_t thickness) {
    uint32_t dx = epaper_abs_delta(x, cx);
    uint32_t dy = epaper_abs_delta(y, cy);
    uint32_t distance_sq = dx * dx + dy * dy;
    uint32_t outer = radius * radius;
    uint32_t inner_radius = radius > thickness ? radius - thickness : 0u;
    uint32_t inner = inner_radius * inner_radius;
    return distance_sq <= outer && distance_sq >= inner;
}

static uint8_t epaper_in_ellipse(uint32_t x, uint32_t y, uint32_t cx, uint32_t cy, uint32_t rx, uint32_t ry) {
    uint32_t dx = epaper_abs_delta(x, cx);
    uint32_t dy = epaper_abs_delta(y, cy);
    return (dx * dx * ry * ry + dy * dy * rx * rx) <= (rx * rx * ry * ry);
}

static uint8_t epaper_ready(const epaper_1in54_t *display) {
    return display != NULL &&
        display->spi_write != NULL &&
        display->cs_write != NULL &&
        display->dc_write != NULL &&
        display->rst_write != NULL &&
        display->busy_read != NULL &&
        display->delay_ms != NULL;
}

static void epaper_send_command(epaper_1in54_t *display, uint8_t command) {
    display->cs_write(0u, display->user);
    display->dc_write(0u, display->user);
    display->spi_write(command, display->user);
    display->cs_write(1u, display->user);
}

static void epaper_send_data(epaper_1in54_t *display, uint8_t data) {
    display->cs_write(0u, display->user);
    display->dc_write(1u, display->user);
    display->spi_write(data, display->user);
    display->cs_write(1u, display->user);
}

static void epaper_wait_until_idle(epaper_1in54_t *display) {
    uint32_t timeout = 10000u;
    while (timeout--) {
        uint8_t busy = display->busy_read(display->user);
        if (display->busy_active_high ? !busy : busy) {
            return;
        }
        display->delay_ms(1u, display->user);
    }
}

void epaper_1in54_reset(epaper_1in54_t *display) {
    if (!epaper_ready(display)) {
        return;
    }
    display->rst_write(1u, display->user);
    display->delay_ms(10u, display->user);
    display->rst_write(0u, display->user);
    display->delay_ms(10u, display->user);
    display->rst_write(1u, display->user);
    display->delay_ms(10u, display->user);
}

void epaper_1in54_init(epaper_1in54_t *display) {
    if (!epaper_ready(display)) {
        return;
    }

    epaper_1in54_reset(display);
    epaper_wait_until_idle(display);

    epaper_send_command(display, 0x01u);
    epaper_send_data(display, 0xC7u);
    epaper_send_data(display, 0x00u);
    epaper_send_data(display, 0x01u);

    epaper_send_command(display, 0x11u);
    epaper_send_data(display, 0x01u);

    epaper_send_command(display, 0x44u);
    epaper_send_data(display, 0x00u);
    epaper_send_data(display, 0x18u);

    epaper_send_command(display, 0x45u);
    epaper_send_data(display, 0xC7u);
    epaper_send_data(display, 0x00u);
    epaper_send_data(display, 0x00u);
    epaper_send_data(display, 0x00u);

    epaper_send_command(display, 0x3Cu);
    epaper_send_data(display, 0x01u);

    epaper_send_command(display, 0x18u);
    epaper_send_data(display, 0x80u);

    epaper_send_command(display, 0x4Eu);
    epaper_send_data(display, 0x00u);
    epaper_send_command(display, 0x4Fu);
    epaper_send_data(display, 0xC7u);
    epaper_send_data(display, 0x00u);
    epaper_wait_until_idle(display);
}

void epaper_1in54_stream(epaper_1in54_t *display, epaper_1in54_pixel_fn pixel, void *pixel_user) {
    if (!epaper_ready(display) || pixel == NULL) {
        return;
    }

    epaper_send_command(display, 0x24u);
    for (uint16_t y = 0u; y < EPAPER_1IN54_HEIGHT; y++) {
        for (uint16_t x_byte = 0u; x_byte < EPAPER_1IN54_BYTES_PER_ROW; x_byte++) {
            uint8_t value = 0xFFu;
            uint16_t base_x = (uint16_t)(x_byte * 8u);
            for (uint8_t bit = 0u; bit < 8u; bit++) {
                if (pixel((uint16_t)(base_x + bit), y, pixel_user)) {
                    value &= (uint8_t)~(0x80u >> bit);
                }
            }
            epaper_send_data(display, value);
        }
    }
}

void epaper_1in54_refresh(epaper_1in54_t *display) {
    if (!epaper_ready(display)) {
        return;
    }
    epaper_send_command(display, 0x22u);
    epaper_send_data(display, 0xF7u);
    epaper_send_command(display, 0x20u);
    epaper_wait_until_idle(display);
}

void epaper_1in54_sleep(epaper_1in54_t *display) {
    if (!epaper_ready(display)) {
        return;
    }
    epaper_send_command(display, 0x10u);
    epaper_send_data(display, 0x01u);
}

static uint8_t epaper_clear_pixel(uint16_t x, uint16_t y, void *user) {
    (void)x;
    (void)y;
    return user != NULL ? 1u : 0u;
}

void epaper_1in54_clear(epaper_1in54_t *display, uint8_t black) {
    epaper_1in54_stream(display, epaper_clear_pixel, black ? display : NULL);
    epaper_1in54_refresh(display);
}

static uint8_t epaper_pattern_pixel(uint16_t x, uint16_t y, void *user) {
    (void)user;
    if (x < 8u || x >= (EPAPER_1IN54_WIDTH - 8u) || y < 8u || y >= (EPAPER_1IN54_HEIGHT - 8u)) {
        return 1u;
    }
    return (uint8_t)((((x >> 4) + (y >> 4)) & 1u) != 0u);
}

void epaper_1in54_draw_pattern(epaper_1in54_t *display) {
    epaper_1in54_stream(display, epaper_pattern_pixel, NULL);
    epaper_1in54_refresh(display);
}

static uint8_t epaper_smile_pixel(uint16_t x, uint16_t y, void *user) {
    (void)user;

    if (epaper_in_ring(x, y, 100u, 100u, 78u, 5u)) {
        return 1u;
    }

    if (epaper_in_ellipse(x, y, 72u, 82u, 10u, 14u) || epaper_in_ellipse(x, y, 128u, 82u, 10u, 14u)) {
        return 1u;
    }

    if (x >= 54u && x <= 146u && y >= 112u && y <= 154u) {
        uint32_t dx = epaper_abs_delta(x, 100u);
        uint32_t curve_y = 150u - ((dx * dx) >> 6);
        if (epaper_abs_delta(y, curve_y) <= 4u) {
            return 1u;
        }
    }

    return 0u;
}

void epaper_1in54_draw_smile(epaper_1in54_t *display) {
    epaper_1in54_stream(display, epaper_smile_pixel, NULL);
    epaper_1in54_refresh(display);
}

epaper_1in54_info_t epaper_1in54_info(void) {
    epaper_1in54_info_t info;
    info.width = EPAPER_1IN54_WIDTH;
    info.height = EPAPER_1IN54_HEIGHT;
    info.bytes_per_row = EPAPER_1IN54_BYTES_PER_ROW;
    info.framebuffer_required = 0u;
    return info;
}
