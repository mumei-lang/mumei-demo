atom deref(present: bool) -> bool
    requires: present;
    ensures: result;
    body: { true }

atom viewItem(has_supplier: bool, supplier_name: i64) -> i64
    requires: true;
    ensures: has_supplier == false => result == 0;
    body: {
        let touched = deref(has_supplier);
        supplier_name
    }
