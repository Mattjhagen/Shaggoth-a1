import Foundation

struct ProviderMetadata: Codable, Identifiable {
    let id: String
    let name: String
    let models: [ModelMetadata]
    let configured: Bool?
    let requiresKey: Bool?
}

struct ModelMetadata: Codable, Identifiable {
    let id: String
    let name: String

    var identifier: String { id }
}
