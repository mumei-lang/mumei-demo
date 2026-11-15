// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract DemoCounter {
    uint256 private total;

    function add(uint256 a, uint256 b) public pure returns (uint256) {
        return a + b;
    }

    function next(uint256 current) public pure returns (uint256) {
        return add(current, 1);
    }
}
