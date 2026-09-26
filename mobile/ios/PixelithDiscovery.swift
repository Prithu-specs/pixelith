// SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
// Copyright (c) 2026 PGA Tech Solutions. See LICENSE.
import Foundation
import Network

/// Bonjour discovery used by the native iOS companion shell.
final class PixelithDiscovery: ObservableObject {
    struct Desktop: Identifiable, Equatable {
        let id: String
        let name: String
        let endpoint: NWEndpoint
    }

    @Published private(set) var desktops: [Desktop] = []
    private var browser: NWBrowser?

    func start() {
        let parameters = NWParameters.tcp
        parameters.includePeerToPeer = true
        let browser = NWBrowser(for: .bonjour(type: "_pixelith._tcp", domain: nil),
                                using: parameters)
        browser.browseResultsChangedHandler = { [weak self] results, _ in
            let found = results.compactMap { result -> Desktop? in
                guard case let .service(name, _, _, _) = result.endpoint else { return nil }
                return Desktop(id: String(describing: result.endpoint), name: name,
                               endpoint: result.endpoint)
            }.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
            DispatchQueue.main.async { self?.desktops = found }
        }
        browser.stateUpdateHandler = { _ in }
        browser.start(queue: .main)
        self.browser = browser
    }

    func stop() {
        browser?.cancel()
        browser = nil
        desktops = []
    }
}
