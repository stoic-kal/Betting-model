import Foundation

enum APIError:LocalizedError { case invalidURL,badResponse,server(String);var errorDescription:String?{switch self{case .invalidURL:"The backend address is invalid.";case .badResponse:"The server returned an unexpected response.";case .server(let m):m}} }
struct APIClient {
    let baseURL:String
    private func fetch<T:Decodable>(_ path:String,as:T.Type) async throws->T {
        guard let url=URL(string:baseURL.trimmingCharacters(in:.whitespacesAndNewlines)+path) else{throw APIError.invalidURL}
        var request=URLRequest(url:url);request.cachePolicy = .reloadIgnoringLocalCacheData;request.timeoutInterval=15
        let(data,response)=try await URLSession.shared.data(for:request);guard let http=response as? HTTPURLResponse else{throw APIError.badResponse};guard(200..<300).contains(http.statusCode)else{throw APIError.server("Server error \(http.statusCode)")};return try JSONDecoder().decode(T.self,from:data)
    }
    func todaySlate()async throws->MobileSlateResponse{try await fetch("/api/mobile-slate",as:MobileSlateResponse.self)}
    func records()async throws->RecordResponse{try await fetch("/api/record-tracker?version=v3",as:RecordResponse.self)}
    func insights()async throws->LossReviewResponse{try await fetch("/api/loss-review?version=v3",as:LossReviewResponse.self)}
}
