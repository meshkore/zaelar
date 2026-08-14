#
# connectors — zaelar external connectors (3rd I/O next to voice + chat): personal messaging (whatsapp/telegram/
# email over the shared messaging layer), music (spotify), cluster channel (meshkore), and code provider
# (architect). Regular package (not namespace) so `connectors.email` is our subpackage and does NOT collide with
# stdlib `email` when collecting tests. See .meshkore/docs/modules/zaelar-modules.md §Connectors.
#
