import SwiftUI

@main
struct JingleezMobileApp: App {
    @StateObject private var settings = AppSettings()
    var body: some Scene { WindowGroup { RootView().environmentObject(settings).preferredColorScheme(.dark) } }
}
