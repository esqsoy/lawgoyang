// PDF 글자층을 쪽마다 뽑는다. 글자층이 없는 쪽은 --ocr로 맥 Vision OCR(한국어·영어)을 돌린다.
//
// 만들기: swiftc -O pipeline/exams/pdftext.swift -o <저장소 밖 폴더>/pdftext
// 쓰기:   pdftext <file.pdf> [--ocr] [--min 40]
//   첫 줄 "PAGES\t<n>", 쪽마다 "=== PAGE <i> [text|ocr|empty]" 머리 뒤에 그 쪽 글자.
//   --ocr: 글자층 글자(공백 뺀 수)가 --min(기본 40)보다 적은 쪽을 300dpi로 그려 OCR한다.
// 기출 원문과 뽑은 글자는 저장소에 넣지 않는다(PRINCIPLES 4).
import AppKit
import Foundation
import PDFKit
import Vision

let args = CommandLine.arguments
guard args.count >= 2, let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else {
    FileHandle.standardError.write("usage: pdftext <file.pdf> [--ocr] [--min 40]\n".data(using: .utf8)!)
    exit(2)
}
let useOCR = args.contains("--ocr")
var minChars = 40
if let i = args.firstIndex(of: "--min"), i + 1 < args.count, let v = Int(args[i + 1]) { minChars = v }

func ocr(_ page: PDFPage) -> String {
    let box = page.bounds(for: .mediaBox)
    let scale: CGFloat = 300.0 / 72.0
    let w = Int(box.width * scale), h = Int(box.height * scale)
    guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { return "" }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.scaleBy(x: scale, y: scale)
    ctx.translateBy(x: -box.origin.x, y: -box.origin.y)
    page.draw(with: .mediaBox, to: ctx)
    guard let img = ctx.makeImage() else { return "" }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["ko-KR", "en-US"]
    req.usesLanguageCorrection = true
    try? VNImageRequestHandler(cgImage: img, options: [:]).perform([req])
    let obs = (req.results ?? []).sorted {
        // 위에서 아래, 같은 줄이면 왼쪽부터 (Vision 좌표는 아래가 0)
        abs($0.boundingBox.midY - $1.boundingBox.midY) > 0.006
            ? $0.boundingBox.midY > $1.boundingBox.midY
            : $0.boundingBox.minX < $1.boundingBox.minX
    }
    return obs.compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
}

print("PAGES\t\(doc.pageCount)")
for i in 0..<doc.pageCount {
    guard let page = doc.page(at: i) else { continue }
    let s = page.string ?? ""
    let n = s.filter { !$0.isWhitespace }.count
    if n >= minChars || !useOCR {
        print("=== PAGE \(i + 1) \(n > 0 ? "text" : "empty")")
        print(s)
    } else {
        print("=== PAGE \(i + 1) ocr")
        print(ocr(page))
    }
}
