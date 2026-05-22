CXX := g++
CXXFLAGS := -O2 -std=c++11 -Wall -Wextra

BINDIR := ../bin

E1_DIR := ../../E1/extracted
E2_DIR := ../../E2/extracted/E2-demo
E3_DIR := ../../E3/extracted/E3-demo

E1_TARGET := $(BINDIR)/e1_ctl
E2_TARGET := $(BINDIR)/e2_ctl
E3_TARGET := $(BINDIR)/e3_ctl

.PHONY: all clean

all: $(E1_TARGET) $(E2_TARGET) $(E3_TARGET)

$(BINDIR):
	mkdir -p $(BINDIR)

$(E1_TARGET): e1_ctl.cpp $(E1_DIR)/e1.cpp $(E1_DIR)/i2c.cpp $(E1_DIR)/i2c_probe.cpp | $(BINDIR)
	$(CXX) $(CXXFLAGS) -I$(E1_DIR) -o $@ $^

$(E2_TARGET): e2_ctl.cpp $(E2_DIR)/e2.cpp $(E2_DIR)/i2c.cpp $(E2_DIR)/i2c_probe.cpp | $(BINDIR)
	$(CXX) $(CXXFLAGS) -I$(E2_DIR) -o $@ $^

$(E3_TARGET): e3_ctl.cpp $(E3_DIR)/e3.cpp $(E3_DIR)/i2c.cpp $(E3_DIR)/i2c_probe.cpp | $(BINDIR)
	$(CXX) $(CXXFLAGS) -I$(E3_DIR) -o $@ $^

clean:
	rm -rf $(BINDIR)
