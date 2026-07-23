import Foundation
import Supabase

struct SupabaseKeychainStorage: AuthLocalStorage {
    private let store = KeychainSessionStore()

    func store(key: String, value: Data) throws {
        try store.store(key: key, value: value)
    }

    func retrieve(key: String) throws -> Data? {
        return try store.retrieve(key: key)
    }

    func remove(key: String) throws {
        try store.remove(key: key)
    }
}

class SupabaseClientManager {
    static let shared = SupabaseClientManager()

    let client: SupabaseClient

    private init() {
        client = SupabaseClient(
            supabaseURL: Environment.current.supabaseURL,
            supabaseKey: Environment.current.supabaseAnonKey,
            options: SupabaseClientOptions(
                auth: .init(
                    storage: SupabaseKeychainStorage()
                )
            )
        )
    }
}

let supabaseClient = SupabaseClientManager.shared.client
