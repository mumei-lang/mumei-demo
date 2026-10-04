package main

import (
	"fmt"
	"strings"
	"testing"
	"time"
)

var comparisonResult bool

func TestTokenComparison(t *testing.T) {
	stored := strings.Repeat("a", 1<<20)
	first := "b" + stored[1:]
	last := stored[:len(stored)-1] + "b"
	measure := func(candidate string) time.Duration {
		start := time.Now()
		for i := 0; i < 1000; i++ {
			comparisonResult = tokenMatches(candidate, stored)
		}
		return time.Since(start)
	}
	measure(first)
	measure(last)
	firstTime := measure(first)
	lastTime := measure(last)
	ratio := float64(lastTime) / float64(firstTime)
	fmt.Printf("first=%s last=%s ratio=%.1f\n", firstTime, lastTime, ratio)
	if ratio <= 5 {
		t.Fatalf("ratio %.1f did not exceed 5", ratio)
	}
}
