atom deref(present: bool) -> bool
    requires: present;
    ensures: result;
    body: { true }

atom can_read(doc_present: bool, owner_matches: bool, share_ok: bool) -> bool
    requires: true;
    ensures: !doc_present => !result;
    body: {
        if !doc_present { false } else { if owner_matches { true } else { share_ok } }
    }
