atom deref(present: bool) -> bool
    requires: present;
    ensures: result;
    body: { true }

atom loginHandler(known: bool, password_matches: bool) -> bool
    requires: true;
    ensures: known == false => result == false;
    body: {
        let touched = deref(known);
        password_matches
    }
