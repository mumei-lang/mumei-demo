package counter

func add(a int64, b int64) int64 {
	return a + b
}

func next(n int64) int64 {
	return add(n, 1)
}
