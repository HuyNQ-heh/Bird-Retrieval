"""Interactive, read-only Streamlit demo for bird image retrieval."""

from io import BytesIO
from pathlib import Path

from PIL import Image
import streamlit as st

from indexing.image_io import EXTENSIONS, load_rgb
from search.service import build_index, search_query
from sql.database import ROOT, read_gallery


@st.cache_resource
def gallery():
    return read_gallery()


@st.cache_resource(max_entries=3)
def gallery_index(excluded):
    records, _ = gallery()
    return build_index(records, excluded)


def matching_gallery_ids(upload, records):
    # An uploaded file has no local path. Confirm its contents before excluding an ID.
    matches = []
    for image_id, (path, _, _) in records.items():
        file = ROOT / path
        if file.name == Path(upload.name).name and file.is_file() and file.read_bytes() == upload.getvalue():
            matches.append(image_id)
    return tuple(matches)


def show_results(query, hits):
    if not hits:
        st.info("Kho so sánh chưa có ảnh hợp lệ.")
        return
    st.subheader("Ảnh tương đồng")
    for column, hit in zip(st.columns(len(hits)), hits):
        with column:
            path = ROOT / hit["image_path"]
            if path.is_file():
                st.image(load_rgb(path), width="stretch")
            else:
                st.warning("Thiếu tệp ảnh trong kho.")
            st.markdown(f'**{hit["rank"]}. {hit["species"]}**')
            st.caption(f'Euclid · {hit["distance"]:.6f}')
    with st.expander("Chi tiết phép tính"):
        left, right = st.columns(2)
        left.image(Image.fromarray(query.mask), caption="Mặt nạ trên ảnh đầu vào", width=240)
        right.image(query.normalized, caption="Ảnh truy vấn đã chuẩn hóa · 224 × 224", width=224)
        rows = [{"Hạng": h["rank"], "ID": h["image_id"], "Loài": h["species"],
                 "Hướng": "Gốc" if h["orientation"] == "original" else "Lật ngang",
                 "S_màu": h["S_mau"], "S_kết_cấu": h["S_ket_cau"],
                 "S_hình_dạng": h["S_hinh_dang"], "Euclid": h["distance"]} for h in hits]
        st.dataframe(rows, hide_index=True, width="stretch", column_config={
            name: st.column_config.NumberColumn(format="%.9f")
            for name in ("S_màu", "S_kết_cấu", "S_hình_dạng", "Euclid")})
        first = hits[0]
        st.markdown(f'**Phép tính hạng 1 · {first["species"]}**')
        st.code(f'd = √({first["S_mau"]!r} + {first["S_ket_cau"]!r} + {first["S_hinh_dang"]!r})'
                f' ≈ {first["distance"]!r}', language=None)


def clear_result():
    st.session_state.pop("result", None)


def main():
    st.set_page_config(page_title="Tìm ảnh chim tương đồng", layout="wide")
    st.title("Tìm ảnh chim tương đồng")
    upload_col, preview_col = st.columns([2, 1])
    upload = upload_col.file_uploader("Chọn ảnh có một con chim", type=list(EXTENSIONS),
                                      on_change=clear_result)
    if upload is None:
        upload_col.button("Tìm ảnh tương đồng", type="primary", disabled=True)
        return
    try:
        preview = load_rgb(BytesIO(upload.getvalue()), supported_only=True)
        preview.thumbnail((400, 240))
        preview_col.image(preview, caption=upload.name)
    except (OSError, ValueError, Image.DecompressionBombError):
        st.error("Không đọc được ảnh. Hãy chọn tệp còn nguyên vẹn thuộc một trong các định dạng: "
                 + ", ".join(EXTENSIONS) + ".")
        return
    if upload_col.button("Tìm ảnh tương đồng", type="primary", key=f"find_{upload.file_id}"):
        clear_result()
        try:
            with st.spinner("Đang xác định vùng chim và so sánh ảnh…"):
                records, _ = gallery()
                index = gallery_index(matching_gallery_ids(upload, records))
                st.session_state.result = search_query(BytesIO(upload.getvalue()), records, index)
        except (ValueError, RuntimeError, OSError) as exc:
            message = str(exc)
            if message.startswith("No VOC bird"):
                message = "Không phát hiện được chim ở cả hai hướng ảnh với ngưỡng tin cậy 0,35."
            elif message.startswith("No usable bird silhouette"):
                message = "Đã phát hiện chim nhưng không tách được mặt nạ hợp lệ ở cả hai mức đệm."
            st.error(message)
    if "result" in st.session_state:
        show_results(*st.session_state.result)


if __name__ == "__main__":
    main()
