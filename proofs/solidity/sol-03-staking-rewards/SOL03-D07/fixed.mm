atom constructor(same_token: bool, owner_zero: bool) -> bool
    requires: true;
    ensures: same_token == true => result == false;
    body: {
        if same_token || owner_zero { false } else { true }
    }
