// This fixed example must be rejected against the same local requirement.
atom advance_version(version: i64) -> i64
    requires: version >= 0 && version < 9223372036854775807;
    ensures: result == version + 1 && result > version;
    body: { version };
