"""Re-export shim for the credential helpers moved into imbi-common.

The implementation lives in :mod:`imbi_common.plugins.credentials` so
both the API and the gateway share one source. Existing imbi-api
callsites import from this module; the names continue to resolve via
this shim.
"""

from imbi_common.plugins.credentials import (
    get_plugin_configuration_keys,
    get_plugin_credentials,
    patch_plugin_configuration,
)

__all__ = [
    'get_plugin_configuration_keys',
    'get_plugin_credentials',
    'patch_plugin_configuration',
]
