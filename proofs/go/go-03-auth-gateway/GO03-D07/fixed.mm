atom deref(present: bool) -> bool
    requires: present;
    ensures: result;
    body: { true }

atom loginHandler(known: bool, password_matches: bool) -> bool
    requires: true;
    ensures: known == false => result == false;
    body: {
        if known { password_matches } else { false }
    }
