"""Generate an original Chinese TCP knowledge-base seed PDF."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "TCP网络基础-知识库种子资料.pdf"


def build() -> Path:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title-cn", parent=styles["Title"], fontName="STSong-Light", fontSize=25, leading=34, alignment=TA_CENTER, textColor=colors.HexColor("#173F36"), spaceAfter=16)
    h1 = ParagraphStyle("h1-cn", parent=styles["Heading1"], fontName="STSong-Light", fontSize=18, leading=25, textColor=colors.HexColor("#1D6A57"), spaceBefore=7, spaceAfter=10)
    h2 = ParagraphStyle("h2-cn", parent=styles["Heading2"], fontName="STSong-Light", fontSize=13, leading=19, textColor=colors.HexColor("#285E52"), spaceBefore=7, spaceAfter=6)
    body = ParagraphStyle("body-cn", parent=styles["BodyText"], fontName="STSong-Light", fontSize=10.5, leading=18, textColor=colors.HexColor("#263B36"), spaceAfter=7)
    callout = ParagraphStyle("callout-cn", parent=body, leftIndent=10, rightIndent=10, borderColor=colors.HexColor("#B8D8CE"), borderWidth=1, borderPadding=9, backColor=colors.HexColor("#F0F8F5"), spaceBefore=7, spaceAfter=10)
    small = ParagraphStyle("small-cn", parent=body, fontSize=8.5, leading=14, textColor=colors.HexColor("#667A74"))

    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm, topMargin=18 * mm, bottomMargin=17 * mm, title="TCP网络基础知识库种子资料", author="多模态 AI 互动式教学智能体项目组")
    story = [
        Spacer(1, 25 * mm),
        Paragraph("TCP 网络基础", title),
        Paragraph("知识库种子资料 - 教学与检索专用", ParagraphStyle("subtitle", parent=body, fontSize=14, alignment=TA_CENTER, textColor=colors.HexColor("#55756C"))),
        Spacer(1, 14 * mm),
        Paragraph("用途说明", h1),
        Paragraph("本资料为项目原创内容，用于验证多模态教学智能体的资料解析、知识库灌入、混合检索与证据引用链路。建议检索词：TCP三次握手、四次挥手、可靠传输、滑动窗口、拥塞控制。", callout),
        Paragraph("学习目标", h1),
        Paragraph("1. 解释 TCP 面向连接、可靠、有序和字节流的核心特征。<br/>2. 能按报文顺序描述 TCP 三次握手与四次挥手。<br/>3. 理解序列号、确认号、重传、流量控制和拥塞控制的协同关系。<br/>4. 能从抓包现象判断连接建立或释放阶段。", body),
        Spacer(1, 12 * mm),
        Paragraph("关键词", h2),
        Paragraph("TCP · SYN · ACK · FIN · sequence number · acknowledgement number · RTT · retransmission · sliding window · congestion window", body),
        Spacer(1, 28 * mm),
        Paragraph("原创教学资料，可安全纳入团队仓库与演示知识库。", small),
        PageBreak(),
        Paragraph("1. TCP 三次握手", h1),
        Paragraph("TCP 三次握手用于在通信双方之间建立可靠连接，并同步双方的初始序列号。三次交互可以证明客户端和服务端的发送与接收能力均可用，同时为后续字节流确定序列空间。", body),
    ]

    handshake = [
        [Paragraph("步骤", h2), Paragraph("报文与状态", h2), Paragraph("教学解释", h2)],
        [Paragraph("1", body), Paragraph("客户端 → 服务端：SYN=1，seq=x<br/>客户端进入 SYN-SENT", body), Paragraph("客户端提出建立连接，并声明自己的初始序列号 x。SYN 报文本身占用一个序列号。", body)],
        [Paragraph("2", body), Paragraph("服务端 → 客户端：SYN=1，ACK=1，seq=y，ack=x+1<br/>服务端进入 SYN-RECEIVED", body), Paragraph("服务端确认已收到客户端请求，同时发送自己的同步请求和初始序列号 y。", body)],
        [Paragraph("3", body), Paragraph("客户端 → 服务端：ACK=1，seq=x+1，ack=y+1<br/>双方进入 ESTABLISHED", body), Paragraph("客户端确认服务端的同步请求。服务端收到后，连接建立完成，可以传输应用数据。", body)],
    ]
    table = Table(handshake, colWidths=[17 * mm, 67 * mm, 75 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEFE9")),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#ABCAC0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([
        table,
        Spacer(1, 7 * mm),
        Paragraph("为什么不能只握手两次？", h2),
        Paragraph("两次握手只能让客户端确认服务端收到了自己的请求，服务端仍无法确认客户端是否收到了服务端的同步响应。第三次 ACK 让服务端获得这一确认，也能降低旧的、延迟到达的 SYN 被误判为新连接的风险。", callout),
        Paragraph("抓包观察要点", h2),
        Paragraph("观察 flags、Seq、Ack 与相对序列号：第一包通常是 [SYN]，第二包是 [SYN, ACK]，第三包是 [ACK]。如果出现多次 SYN 且无 SYN-ACK，应检查目标端口、路由、防火墙或服务监听状态。", body),
        PageBreak(),
        Paragraph("2. 连接释放与可靠传输", h1),
        Paragraph("TCP 常用四次挥手释放全双工连接。主动关闭方发送 FIN；被动关闭方先 ACK 确认，待自身数据发送完毕后再发送 FIN；主动关闭方回复最后一个 ACK，并进入 TIME-WAIT。TIME-WAIT 通常持续 2MSL，用于确保最后的 ACK 有机会重传，并让旧连接报文在网络中消失。", body),
        Paragraph("3. 可靠性机制", h1),
        Paragraph("序列号与确认号：每个字节属于序列空间，累计确认表示接收方期望的下一个字节。<br/>超时重传与快速重传：发送方根据 RTT 估算重传超时；多个重复 ACK 可触发快速重传。<br/>校验和：用于检测 TCP 首部和数据在传输中的比特错误。<br/>有序交付：乱序到达的数据先缓存，缺口补齐后再按序交付应用。", body),
        Paragraph("4. 流量控制与拥塞控制", h1),
        Paragraph("流量控制通过接收窗口 rwnd 避免发送方压垮接收方；拥塞控制通过拥塞窗口 cwnd 避免向网络注入过多数据。实际可发送窗口通常受 min(rwnd, cwnd) 限制。慢启动、拥塞避免、快速重传与快速恢复共同调整 cwnd。", body),
        Paragraph("课堂检索问题", h1),
        Paragraph("• TCP 三次握手每一步的标志位、序列号与确认号是什么？<br/>• 为什么建立连接需要三次而不是两次？<br/>• TIME-WAIT 的作用是什么？<br/>• rwnd 与 cwnd 分别解决什么问题？<br/>• 抓包中连续 SYN 重传可能说明什么？", callout),
        Paragraph("索引建议", h2),
        Paragraph("按标题和段落切分，目标块大小约 300-500 tokens，保留页码与章节标题。推荐将“TCP 三次握手”表格作为独立证据块，并保留 source_ref 与 page_ref，便于课件节点引用。", body),
        Spacer(1, 8 * mm),
        Paragraph("版本：1.0 · 生成用途：模块三知识库灌入与检索验收", small),
    ])

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("STSong-Light", 8)
        canvas.setFillColor(colors.HexColor("#789087"))
        canvas.drawString(20 * mm, 10 * mm, "多模态 AI 互动式教学智能体")
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"第 {document.page} 页")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return OUTPUT


if __name__ == "__main__":
    print(build())
