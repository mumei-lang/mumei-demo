pub fn late_fee(days_late: i64, daily_rate: i64) -> i64 {
    if days_late < 0 {
        panic!("days_late must be non-negative");
    }
    days_late * daily_rate
}

#[cfg(test)]
mod tests {
    use super::late_fee;

    #[test]
    fn late_fee_example() {
        assert_eq!(late_fee(3, 50), 150);
    }

    #[test]
    fn late_fee_relation() {
        assert!(late_fee(10, 20) >= 0);
    }

    #[test]
    #[should_panic]
    fn late_fee_rejects_negative() {
        late_fee(-1, 20);
    }
}
