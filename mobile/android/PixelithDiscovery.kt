// SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
// Copyright (c) 2026 PGA Tech Solutions. See LICENSE.
package solutions.pgatech.pixelith

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo

/** DNS-SD discovery used by the native Android companion shell. */
class PixelithDiscovery(context: Context, private val onFound: (NsdServiceInfo) -> Unit) {
    private val manager = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val listener = object : NsdManager.DiscoveryListener {
        override fun onDiscoveryStarted(type: String) = Unit
        override fun onDiscoveryStopped(type: String) = Unit
        override fun onStartDiscoveryFailed(type: String, code: Int) = stop()
        override fun onStopDiscoveryFailed(type: String, code: Int) = Unit
        override fun onServiceLost(service: NsdServiceInfo) = Unit
        override fun onServiceFound(service: NsdServiceInfo) {
            if (service.serviceType.startsWith("_pixelith._tcp")) onFound(service)
        }
    }
    fun start() = manager.discoverServices("_pixelith._tcp.", NsdManager.PROTOCOL_DNS_SD, listener)
    fun stop() = runCatching { manager.stopServiceDiscovery(listener) }.getOrNull()
}
