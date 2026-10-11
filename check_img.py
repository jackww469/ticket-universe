"""JPG 的 SOF0/SOF2 段包含尺寸"""
with open(r'D:/ticket-universe/empty-state.png', 'rb') as f:
    data = f.read()

# 找到 SOF 标记 (0xFFC0 - 0xFFCF, 除 0xFFC4 0xFFC8 0xFFCC)
i = 0
while i < len(data) - 8:
    if data[i] == 0xFF and 0xC0 <= data[i+1] <= 0xCF and data[i+1] not in (0xC4, 0xC8, 0xCC):
        # length in big-endian
        import struct
        h = struct.unpack('>H', data[i+5:i+7])[0]
        w = struct.unpack('>H', data[i+7:i+9])[0]
        print(f'JPEG Size: {w} x {h}')
        break
    i += 1
else:
    print('SOF not found')
