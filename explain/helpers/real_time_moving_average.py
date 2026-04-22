"""RealTimeMovingAverage — port of src/explain/helpers/RealTimeMovingAverage.js

Fixed-window circular-buffer moving average. addValue(x) returns the new
average after pushing x. Matches JS semantics including the count-growing
phase before the buffer is full.
"""

from __future__ import annotations


class RealTimeMovingAverage:
    def __init__(self, windowSize):
        self.windowSize = max(1, int(windowSize))
        self.values = [None] * self.windowSize
        self.count = 0
        self.writeIndex = 0
        self.sum = 0
        self.currentAverage = 0

    def addValue(self, newValue):
        if self.count < self.windowSize:
            self.values[self.writeIndex] = newValue
            self.sum += newValue
            self.count += 1
        else:
            oldestValue = self.values[self.writeIndex]
            self.values[self.writeIndex] = newValue
            self.sum += newValue - oldestValue

        self.writeIndex = (self.writeIndex + 1) % self.windowSize
        self.currentAverage = self.sum / self.count
        return self.currentAverage

    def getCurrentAverage(self):
        return self.currentAverage

    def reset(self):
        self.values = [None] * self.windowSize
        self.count = 0
        self.writeIndex = 0
        self.sum = 0
        self.currentAverage = 0
