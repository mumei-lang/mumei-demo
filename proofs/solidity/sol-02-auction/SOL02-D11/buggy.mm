struct Outbid {
    bid_of: i64,
    pending: i64,
}

atom bid(has_previous: bool, prev_bid_of: i64, prev_pending: i64) -> Outbid
    requires: prev_bid_of >= 0 && prev_pending >= 0;
    ensures: has_previous => result.bid_of == 0;
    body: {
        Outbid { bid_of: prev_bid_of, pending: prev_pending }
    }
