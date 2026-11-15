package main

// Declared Go unit for the audit --enable-summaries demo.
func Add(a, b int64) int64 {
	return a + b
}

func Next(n int64) int64 {
	return Add(n, 1)
}
