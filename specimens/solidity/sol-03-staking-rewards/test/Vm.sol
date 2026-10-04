// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Minimal cheatcode interface for the Foundry test environment.
interface Vm {
    function deal(address account, uint256 amount) external;
    function prank(address msgSender) external;
    function prank(address msgSender, address txOrigin) external;
    function startPrank(address msgSender) external;
    function startPrank(address msgSender, address txOrigin) external;
    function stopPrank() external;
    function warp(uint256 timestamp) external;
    function roll(uint256 blockNumber) external;
    function load(address account, bytes32 slot) external returns (bytes32 value);
    function sign(uint256 privateKey, bytes32 digest)
        external
        returns (uint8 v, bytes32 r, bytes32 s);
    function addr(uint256 privateKey) external returns (address);
    function expectRevert() external;
    function expectRevert(bytes4 selector) external;
}
