// A local arithmetic contract, not a proof of Python authorization or locking.
atom advance_version(version: i64) -> i64
    requires: version >= 0 && version < 9223372036854775807;
    ensures: result == version + 1 && result > version;
    body: { version + 1 };
