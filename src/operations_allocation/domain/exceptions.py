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
