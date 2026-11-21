pragma solidity ^0.8.0;

contract BindingReport {
    function answer() internal pure returns (uint256) {
        return 42;
    }

    function useAnswer() external pure returns (uint256) {
        return answer() + missingName;
    }
}
