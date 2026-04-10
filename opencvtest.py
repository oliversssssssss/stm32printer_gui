import cv2
import numpy as np

# =========================
# 参数区
# =========================
input_path = "C:\\NewFiles\\printer_gui_pc\\image.png"      # 输入图片
target_width = 88            # 固定宽度
target_height = 66           # 固定高度
threshold_value = 122         # 二值化阈值

# 黑色像素是否记为1
# True: 黑=1, 白=0
# False: 白=1, 黑=0
black_as_one = True

# 是否显示窗口
show_window = True

# =========================
# 1. 读取灰度图
# =========================
img = cv2.imread(input_path, cv2.IMREAD_GRAYSCALE)
if img is None:
    raise FileNotFoundError(f"无法读取图片: {input_path}")

# =========================
# 2. resize 到固定分辨率
# =========================
img_resized = cv2.resize(
    img,
    (target_width, target_height),
    interpolation=cv2.INTER_AREA
)

# =========================
# 3. 二值化
# =========================
_, binary = cv2.threshold(img_resized, threshold_value, 255, cv2.THRESH_BINARY)

# =========================
# 4. 转成点阵数据（0/1）
# =========================
if black_as_one:
    # 黑色像素(0) -> 1，白色像素(255) -> 0
    dot_matrix = (binary == 0).astype(np.uint8)
else:
    # 白色像素(255) -> 1，黑色像素(0) -> 0
    dot_matrix = (binary == 255).astype(np.uint8)

# =========================
# 5. 保存点阵数据到 txt
# =========================
np.savetxt("dot_matrix.txt", dot_matrix, fmt="%d")
print("点阵数据已保存到 dot_matrix.txt")

# =========================
# 6. 打包为字节数据（每8个点 -> 1字节）
#    常见于单片机 / 点阵屏 / 热敏打印头
# =========================
def pack_bits_to_bytes(matrix):
    h, w = matrix.shape

    # 宽度不是8的倍数就补0
    padded_w = ((w + 7) // 8) * 8
    if padded_w != w:
        pad = np.zeros((h, padded_w - w), dtype=np.uint8)
        matrix = np.hstack((matrix, pad))
        w = padded_w

    byte_list = []

    for row in matrix:
        row_bytes = []
        for i in range(0, w, 8):
            byte = 0
            for bit in range(8):
                byte = (byte << 1) | int(row[i + bit])
            row_bytes.append(byte)
        byte_list.append(row_bytes)

    return byte_list

packed_bytes = pack_bits_to_bytes(dot_matrix)

# 保存为十六进制文本
with open("dot_matrix_hex.txt", "w", encoding="utf-8") as f:
    for row in packed_bytes:
        line = " ".join(f"0x{b:02X}" for b in row)
        f.write(line + "\n")

print("字节点阵数据已保存到 dot_matrix_hex.txt")

# =========================
# 7. 显示点阵图
# =========================
# 为了看清楚，把0/1矩阵变成黑白图再放大
if black_as_one:
    # 1表示黑点，所以显示时 1->0(黑), 0->255(白)
    display_img = np.where(dot_matrix == 1, 0, 255).astype(np.uint8)
else:
    # 1表示白点
    display_img = np.where(dot_matrix == 1, 255, 0).astype(np.uint8)

# 放大显示
scale = 10
display_big = cv2.resize(
    display_img,
    (target_width * scale, target_height * scale),
    interpolation=cv2.INTER_NEAREST
)

cv2.imwrite("dot_matrix_preview.png", display_big)
print("点阵预览图已保存到 dot_matrix_preview.png")

if show_window:
    cv2.imshow("Dot Matrix Preview", display_big)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

# =========================
# 8. 控制台打印部分信息
# =========================
print("\n前8行点阵数据示例：")
for row in dot_matrix[:8]:
    print(" ".join(str(x) for x in row))

print("\n前8行十六进制字节示例：")
for row in packed_bytes[:8]:
    print(" ".join(f"0x{b:02X}" for b in row))