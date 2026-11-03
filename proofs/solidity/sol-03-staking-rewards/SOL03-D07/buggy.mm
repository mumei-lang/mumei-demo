atom constructor(same_token: bool, owner_zero: bool) -> bool
    requires: true;
    ensures: same_token == true => result == false;
    body: {
        true
    }
