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


class ArtifactAlreadyExistsError(OperationsAllocationError):
    """Raised when writing an artifact would silently overwrite an existing file."""


class InvalidArtifactFilenameError(OperationsAllocationError):
    """Raised when an artifact filename is unsafe (e.g. attempts path traversal)."""


class ArtifactSourceNotFoundError(OperationsAllocationError):
    """Raised when an imported artifact's source file cannot be found."""


class InvalidQcRuleError(OperationsAllocationError):
    """Raised when a QC rule configuration is structurally invalid or of an
    unsupported/forbidden type."""


class UnsupportedFileFormatError(OperationsAllocationError):
    """Raised when an input file's format is not supported in v1 (e.g. .xls)."""


class ColumnMappingError(OperationsAllocationError):
    """Raised when a required source column cannot be found in an imported file."""
