package com.jarvisos.companion

import android.service.quicksettings.Tile
import android.service.quicksettings.TileService

/**
 * User-visible Quick Settings entry point for the local AI bridge.
 *
 * The tile only asks the app-owned bootstrap boundary to ensure the foreground
 * service is available. It does not interpret prompts, execute tools, or own
 * the server/model lifecycle.
 */
class LocalAIHostTileService : TileService() {

    override fun onStartListening() {
        super.onStartListening()
        updateTile()
    }

    override fun onClick() {
        super.onClick()
        LocalAIHostBootstrap.ensureAvailable(
            this,
            startPath = LocalAIHostBootstrap.StartPath.QUICK_SETTINGS_TILE,
        )
        updateTile()
    }

    private fun updateTile() {
        qsTile?.apply {
            label = getString(R.string.quick_settings_local_ai)
            state = when (currentReadiness()) {
                LocalAIHostReadiness.READY_BRIDGE,
                LocalAIHostReadiness.LOADING_MODEL,
                LocalAIHostReadiness.READY_MODEL,
                LocalAIHostReadiness.BUSY -> Tile.STATE_ACTIVE
                LocalAIHostReadiness.STARTING -> Tile.STATE_UNAVAILABLE
                LocalAIHostReadiness.STOPPED,
                LocalAIHostReadiness.STOPPING,
                LocalAIHostReadiness.ERROR -> Tile.STATE_INACTIVE
            }
            updateTile()
        }
    }

    private fun currentReadiness(): LocalAIHostReadiness =
        (application as? CompanionApplication)?.currentLocalAIHostReadiness()
            ?: LocalAIHostReadiness.STOPPED
}
