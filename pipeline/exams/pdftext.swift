// PDF 글자층을 쪽마다 뽑는다. 글자층이 없는 쪽은 --ocr로 맥 Vision OCR(한국어·영어)을 돌린다.
//
// 만들기: swiftc -O pipeline/exams/pdftext.swift -o <저장소 밖 폴더>/pdftext
// 쓰기:   pdftext <file.pdf> [--ocr] [--min 40] [--from 1] [--to n]
//   첫 줄 "PAGES\t<n>", 쪽마다 "=== PAGE <i> [text|ocr|empty]" 머리 뒤에 그 쪽 글자.
//   --ocr: 글자층 글자(공백 뺀 수)가 --min(기본 40)보다 적은 쪽을 300dpi로 그려 OCR한다.
//   --force: 글자층이 있어도 모든 쪽을 OCR한다(글자층이 깨진 책).
//   --from/--to: 이 쪽 범위만 낸다(1부터). 긴 스캔본은 나눠 돌리거나 끊긴 쪽부터 다시 돈다.
//   쪽마다 메모리를 비우고(autoreleasepool) 바로 내보낸다. 26.11.24에 1,000쪽 넘는 스캔본이
//   메모리가 1.4GB 넘게 불어 도중에 죽고 버퍼에 남은 글자까지 잃어서 고쳤다.
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
let force = args.contains("--force")
let useOCR = args.contains("--ocr") || force
var minChars = 40
if let i = args.firstIndex(of: "--min"), i + 1 < args.count, let v = Int(args[i + 1]) { minChars = v }
var fromPage = 1, toPage = doc.pageCount
if let i = args.firstIndex(of: "--from"), i + 1 < args.count, let v = Int(args[i + 1]) { fromPage = max(1, v) }
if let i = args.firstIndex(of: "--to"), i + 1 < args.count, let v = Int(args[i + 1]) { toPage = min(doc.pageCount, v) }
setvbuf(stdout, nil, _IOLBF, 0)

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
if fromPage <= toPage {
    for i in (fromPage - 1)..<toPage {
        autoreleasepool {
            guard let page = doc.page(at: i) else { return }
            let s = page.string ?? ""
            let n = s.filter { !$0.isWhitespace }.count
            if !force && (n >= minChars || !useOCR) {
                print("=== PAGE \(i + 1) \(n > 0 ? "text" : "empty")")
                print(s)
            } else {
                print("=== PAGE \(i + 1) ocr")
                print(ocr(page))
            }
        }
    }
}
