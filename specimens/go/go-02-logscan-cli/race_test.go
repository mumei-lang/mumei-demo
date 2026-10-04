package main

import (
	"os"
	"strings"
	"testing"
	"time"
)

func TestWorkerCounts(t *testing.T) {
	paths := strings.Split(os.Getenv("GO_TEST_FILES"), ",")
	_, _, err := readFiles(paths, 12, time.Time{}, false)
	if err != nil {
		t.Fatal(err)
	}
}
