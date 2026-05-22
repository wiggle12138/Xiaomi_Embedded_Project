#include <cstdlib>
#include <cstring>
#include <iostream>

#include "../../E1/extracted/e1.h"

extern int led_idx;

static int clamp_int(int value, int min_value, int max_value) {
    if (value < min_value) return min_value;
    if (value > max_value) return max_value;
    return value;
}

static int parse_int(const char *text, int &out) {
    if (text == nullptr) return -1;
    char *end = nullptr;
    long value = std::strtol(text, &end, 10);
    if (end == text || *end != '\0') return -1;
    out = static_cast<int>(value);
    return 0;
}

static void print_usage() {
    std::cout << "Usage:\n"
              << "  e1_ctl off\n"
              << "  e1_ctl rgb <r> <g> <b> [brightness_0_100]\n";
}

int main(int argc, char **argv) {
    if (argc < 2) {
        print_usage();
        return 1;
    }

    i2c_probe_target list[I2C_PROBE_LIST_LEN] = {};
    std::memcpy(list, I2C_PROBE_LIST, sizeof(list));
    i2c_probe(list, I2C_PROBE_LIST_LEN);
    I2c_e1_led_find(list);

    int fd = I2c_open(list[led_idx].path);
    if (fd < 0) {
        std::perror("I2c_open failed");
        return 2;
    }

    I2c_e1_led_init_all(fd, list);

    std::string cmd(argv[1]);
    int rc = 0;

    if (cmd == "off") {
        e1_led_off_all(fd, list);
    } else if (cmd == "rgb") {
        if (argc < 5) {
            print_usage();
            I2c_close(fd);
            return 1;
        }
        int r = 0, g = 0, b = 0, brightness = 100;
        if (parse_int(argv[2], r) || parse_int(argv[3], g) || parse_int(argv[4], b)) {
            std::cerr << "Invalid rgb value\n";
            I2c_close(fd);
            return 1;
        }
        if (argc >= 6 && parse_int(argv[5], brightness)) {
            std::cerr << "Invalid brightness value\n";
            I2c_close(fd);
            return 1;
        }

        r = clamp_int(r, 0, 255);
        g = clamp_int(g, 0, 255);
        b = clamp_int(b, 0, 255);
        brightness = clamp_int(brightness, 0, 100);

        r = (r * brightness) / 100;
        g = (g * brightness) / 100;
        b = (b * brightness) / 100;
        e1_rgb_color_control_all(fd, list, static_cast<uint8_t>(r), static_cast<uint8_t>(g), static_cast<uint8_t>(b));
    } else {
        print_usage();
        rc = 1;
    }

    I2c_close(fd);
    return rc;
}
