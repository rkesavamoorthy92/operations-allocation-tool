"""Application-facing exceptions; persistence details do not escape this layer."""


class OperationsAllocationError(Exception):
    """Base exception for the application."""


class InvalidConfigurationError(OperationsAllocationError):
    """Raised when a program or setup configuration is structurally invalid."""


class InvalidStateTransitionError(OperationsAllocationError):
    """Raised when a Run transition is not permitted."""


class DuplicateRunIdError(OperationsAllocationError):
    """Raised if a Run ID conflicts with an existing immutable Run."""


class InvalidAssociateConfigurationError(OperationsAllocationError):
    """Raised when an associate master or snapshot value is invalid."""


class SnapshotCreationError(OperationsAllocationError):
    """Raised when a frozen snapshot cannot be created."""


class ManifestIntegrityError(OperationsAllocationError):
    """Raised when an execution manifest does not match its snapshot."""


class InvalidRunStateError(OperationsAllocationError):
    """Raised when persistence receives a state outside the approved state set."""


class PersistenceError(OperationsAllocationError):
    """Raised when local persistence cannot complete safely."""


class IdentifierNormalizationError(OperationsAllocationError):
    """Raised when a primary identifier value cannot be normalized."""


class ValidationBlockedError(OperationsAllocationError):
    """Raised when structural Critical validation issues prevent processing."""


class InvalidResolutionError(OperationsAllocationError):
    """Raised when a duplicate-identifier resolution record is malformed."""


class UnresolvedDuplicatesError(OperationsAllocationError):
    """Raised when the eligible population is frozen with unresolved duplicate IDs."""


class SamplingConfigurationError(OperationsAllocationError):
    """Raised when sampling configuration or inputs are invalid for the Randomizer."""


class InsufficientCapacityError(OperationsAllocationError):
    """Raised when total active-associate maximum capacity is below the sample count."""


class AboveTargetConfirmationRequiredError(OperationsAllocationError):
    """Raised when finalizing allocation above target without explicit confirmation."""
