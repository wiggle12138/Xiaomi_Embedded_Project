#include <cstdlib>
#include <cstring>
#include <iostream>

#include "../../E3/extracted/E3-demo/e3.h"

extern int motor_idx;

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
              << "  e3_ctl open\n"
              << "  e3_ctl close\n"
              << "  e3_ctl position <0-100>\n";
}

int main(int argc, char **argv) {
    if (argc < 2) {
        print_usage();
        return 1;
    }

    i2c_probe_target list[I2C_PROBE_LIST_LEN] = {};
    std::memcpy(list, I2C_PROBE_LIST, sizeof(list));
    i2c_probe(list, I2C_PROBE_LIST_LEN);
    I2c_e3_find(list);

    int fd = I2c_open(list[motor_idx].path);
    if (fd < 0) {
        std::perror("I2c_open failed");
        return 2;
    }

    std::string cmd(argv[1]);
    int rc = 0;
    if (cmd == "open") {
        e3_set_position(fd, list[motor_idx].detected_addrs[0], 100);
    } else if (cmd == "close") {
        e3_set_position(fd, list[motor_idx].detected_addrs[0], 0);
    } else if (cmd == "position") {
        if (argc < 3) {
            print_usage();
            I2c_close(fd);
            return 1;
        }
        int pos = 0;
        if (parse_int(argv[2], pos)) {
            std::cerr << "Invalid position value\n";
            I2c_close(fd);
            return 1;
        }
        pos = clamp_int(pos, 0, 100);
        e3_set_position(fd, list[motor_idx].detected_addrs[0], static_cast<char>(pos));
    } else {
        print_usage();
        rc = 1;
    }

    I2c_close(fd);
    return rc;
}
