atom deref(present: bool) -> bool
    requires: present;
    ensures: result;
    body: { true }

atom moveTask(found: bool, can_move: bool) -> bool
    requires: true;
    ensures: found == false => result == false;
    body: {
        if found { can_move } else { false }
    }
