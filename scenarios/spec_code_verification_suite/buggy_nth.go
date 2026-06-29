package lists

func nth(values []int, idx int) int {
	return values[idx] // Bug: no bounds check
}
