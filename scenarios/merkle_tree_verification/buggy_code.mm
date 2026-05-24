// Merkle Tree Verification - buggy implementation
// The verifier tries to accept a Merkle proof without the hash-function
// security/collision-resistance precondition that binds the computed root.

atom verify_merkle_root(
    root: i64,
    leaf: i64,
    sibling_hash: i64,
    expected_root: i64
)
    requires: root >= 0 && leaf >= 0 && sibling_hash >= 0 && expected_root >= 0;
    ensures: result == expected_root;
    body: {
        leaf + sibling_hash
    };
