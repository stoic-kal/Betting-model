import Foundation

@MainActor final class AppSettings: ObservableObject {
    @Published var backendURL: String { didSet { UserDefaults.standard.set(backendURL, forKey: "backendURL") } }
    @Published var unitValue: Double { didSet { UserDefaults.standard.set(unitValue, forKey: "unitValue") } }
    init() {
        backendURL = UserDefaults.standard.string(forKey: "backendURL") ?? "http://127.0.0.1:3000"
        let saved = UserDefaults.standard.double(forKey: "unitValue"); unitValue = saved > 0 ? saved : 20
    }
}
