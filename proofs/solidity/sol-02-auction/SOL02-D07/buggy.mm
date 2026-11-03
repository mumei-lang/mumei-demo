atom init(sender_is_deployer: bool, initialized: bool) -> bool
    requires: true;
    ensures: sender_is_deployer == false => result == false;
    body: {
        initialized == false
    }
