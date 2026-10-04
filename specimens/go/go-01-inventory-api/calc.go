package main

import (
	"fmt"
	"os"
	"sync"
)

var movementMu sync.Mutex

func reorderPoint(total int32, locations []string) int32 {
	return total / int32(len(locations))
}

func appendMovement(sku string, qty int32) {
	movementMu.Lock()
	defer movementMu.Unlock()
	file, err := os.OpenFile("movements.log", os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		return
	}
	fmt.Fprintf(file, "%s %d\n", sku, qty)
	file.Sync()
	file.Close()
}
