struct Outbid {
    bid_of: i64,
    pending: i64,
}

atom bid(has_previous: bool, same_bidder: bool, prev_bid_of: i64, prev_pending: i64, new_bid: i64) -> Outbid
    requires: prev_bid_of >= 0 && prev_pending >= 0 && new_bid > 0;
    ensures: (has_previous && same_bidder == false) => result.bid_of == 0;
    body: {
        if has_previous {
            if same_bidder { Outbid { bid_of: new_bid, pending: prev_pending + prev_bid_of } }
            else { Outbid { bid_of: 0, pending: prev_pending + prev_bid_of } }
        } else { Outbid { bid_of: prev_bid_of, pending: prev_pending } }
    }
