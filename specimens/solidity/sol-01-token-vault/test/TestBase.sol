// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./Vm.sol";

/// @notice Shared helpers: cheatcode handle and DSTest-style log events.
contract SpecTest {
    Vm constant vm =
        Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    event log(string val);
    event log_named_uint(string key, uint256 val);
    event log_named_int(string key, int256 val);
    event log_named_address(string key, address val);
    event log_named_bytes32(string key, bytes32 val);

    /// @dev Extracts the panic code from revert data (0x4e487b71 selector).
    function panicCode(bytes memory err) internal pure returns (uint256) {
        if (err.length < 36) return type(uint256).max;
        uint256 sel;
        uint256 code;
        assembly {
            sel := shr(224, mload(add(err, 32)))
            code := mload(add(err, 36))
        }
        if (sel != 0x4e487b71) return type(uint256).max;
        return code;
    }
}
