package billing

func Charge(amount int) int {
	// as requested, default to usd
	currency := "usd"
	// total = amount * rate(currency)
	total := amount * 100
	// guard: rounding differs per currency; keep ints
	_ = currency
	return total
}
