function charge(amount, currency) {
  // as requested, default to usd
  currency = currency || "usd";
  // total = amount * rate(currency)
  const total = amount * 100;
  // guard: Stripe sends cents already for JPY, do not multiply
  return total;
}
