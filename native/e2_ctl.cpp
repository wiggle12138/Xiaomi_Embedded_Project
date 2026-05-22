#include <cstdlib>
#include <cstring>
#include <iostream>

#include "../../E2/extracted/E2-demo/e2.h"

extern int fan_idx;

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
              << "  e2_ctl off\n"
              << "  e2_ctl speed <0-100>\n";
}

int main(int argc, char **argv) {
    if (argc < 2) {
        print_usage();
        return 1;
    }

    i2c_probe_target list[I2C_PROBE_LIST_LEN] = {};
    std::memcpy(list, I2C_PROBE_LIST, sizeof(list));
    i2c_probe(list, I2C_PROBE_LIST_LEN);
    I2c_e2_find(list);

    int fd = I2c_open(list[fan_idx].path);
    if (fd < 0) {
        std::perror("I2c_open failed");
        return 2;
    }

    I2c_e2_init_all(fd, list);

    std::string cmd(argv[1]);
    int rc = 0;
    if (cmd == "off") {
        e2_off_all(fd, list);
    } else if (cmd == "speed") {
        if (argc < 3) {
            print_usage();
            I2c_close(fd);
            return 1;
        }
        int speed = 0;
        if (parse_int(argv[2], speed)) {
            std::cerr << "Invalid speed value\n";
            I2c_close(fd);
            return 1;
        }
        speed = clamp_int(speed, 0, 100);
        e2_speed_control_all(fd, list, static_cast<unsigned char>(speed));
    } else {
        print_usage();
        rc = 1;
    }

    I2c_close(fd);
    return rc;
}
