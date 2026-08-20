from api import common
from api.common import *  # noqa: F401,F403
from api.common import api, logger, auth_required, role_required, log_action
from api.common import (
    _check_login_rate_limit,
    _audit_login_failure,
    _validate_password_strength,
    _fallback_knowledge_search,
)

# ===================================================================
# 5. 知识库路由 (Knowledge Base Routes)
# ===================================================================

@api.route("/knowledge/upload", methods=["POST"])
@role_required(["super_admin", "student_affairs"])
@log_action("上传知识库文档")
def upload_knowledge():
    """上传文档到知识库。"""
    if "file" not in request.files:
        return jsonify({"success": False, "message": "请上传文件"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"success": False, "message": "文件名不能为空"}), 400

    allowed_ext = {".txt", ".pdf", ".docx", ".doc", ".md"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        return jsonify({
            "success": False,
            "message": "不支持的文件格式 '{}'，允许：{}".format(ext, ", ".join(allowed_ext)),
        }), 400

    try:
        # Save uploaded file to docs directory
        docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
        os.makedirs(docs_dir, exist_ok=True)
        save_path = os.path.join(docs_dir, file.filename)
        file.save(save_path)

        # Index the document
        result = common.knowledge_base.incremental_update(save_path)
        doc_id = result.get("doc_id", file.filename)

        return jsonify({
            "success": True,
            "message": "文档上传并索引成功",
            "data": {"document_id": doc_id, "filename": file.filename},
        }), 201
    except Exception as exc:
        logger.error("文档上传失败: %s", exc)
        return jsonify({"success": False, "message": "文档上传失败: " + "内部错误，请稍后重试"}), 500

@api.route("/knowledge/documents", methods=["GET"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("查看知识库文档列表")
def list_documents():
    """列出已索引的知识库文档。"""
    try:
        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))

        # 优先使用文档级索引，返回真实文件名和创建时间；旧索引兜底。
        seen = {}
        for did, info in getattr(common.knowledge_base, "_doc_index", {}).items():
            seen[did] = {
                "doc_id": did,
                "filename": info.get("source") or did,
                "chunk_count": info.get("chunk_count", 0),
                "created_at": info.get("created_at", ""),
            }
        if not seen:
            for item in common.knowledge_base._documents:
                did = item.get("doc_id", "unknown")
                if did not in seen:
                    seen[did] = {
                        "doc_id": did,
                        "filename": item.get("metadata", {}).get("source") or did,
                        "chunk_count": 0,
                        "created_at": item.get("metadata", {}).get("created_at", ""),
                    }
                seen[did]["chunk_count"] += 1
        docs = list(seen.values())
        total = len(docs)
        start = (page - 1) * per_page
        items = docs[start:start + per_page]
        return jsonify({"success": True, "data": items, "total": total}), 200
    except Exception as exc:
        logger.error("获取文档列表失败: %s", exc)
        return jsonify({"success": False, "message": "获取文档列表失败"}), 500


@api.route("/knowledge/documents/<string:document_id>", methods=["DELETE"])
@role_required(["super_admin"])
@log_action("删除知识库文档")
def delete_document(document_id):
    """从知识库中删除指定文档。"""
    try:
        result = common.knowledge_base.delete_document(document_id)
        if result.get("status") not in ("deleted",):
            return jsonify({"success": False, "message": "文档不存在"}), 404
        return jsonify({"success": True, "message": "文档已删除"}), 200
    except Exception as exc:
        logger.error("删除文档失败: %s", exc)
        return jsonify({"success": False, "message": "删除失败，请稍后重试"}), 500


@api.route("/knowledge/search", methods=["POST"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("搜索知识库")
def search_knowledge():
    """在知识库中检索相关内容。"""
    data = request.get_json(silent=True)
    if not data or not data.get("query"):
        return jsonify({"success": False, "message": "请输入搜索关键词"}), 400

    query = data["query"]
    top_k = min(20, max(1, data.get("top_k", 5)))

    try:
        if common.knowledge_base is not None:
            hits = common.knowledge_base.search(query, top_k=top_k)
            results = [
                {
                    "doc_id": hit.get("metadata", {}).get("source", "unknown"),
                    "score": round(hit.get("score", 0), 3),
                    "content": hit.get("content", ""),
                    "snippet": hit.get("content", "")[:300],
                    "source": hit.get("metadata", {}).get("source", "unknown"),
                }
                for hit in hits
            ]
            if not results:
                results = [{
                    "doc_id": "无匹配", "score": 0,
                    "content": "知识库中暂无与您搜索相关的内容",
                    "snippet": "请先上传相关文档到知识库", "source": "system",
                }]
        else:
            results = _fallback_knowledge_search(query, top_k)
        return jsonify({
            "success": True,
            "data": results,
            "query": query,
        }), 200
    except Exception as exc:
        logger.warning("RAG搜索失败，使用关键词后备: %s", exc)
        try:
            results = _fallback_knowledge_search(query, top_k)
            return jsonify({"success": True, "data": results, "query": query, "source": "keyword_fallback"}), 200
        except Exception as e2:
            return jsonify({"success": False, "message": "搜索失败，请稍后重试"}), 500


@api.route("/knowledge/stats", methods=["GET"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("查看知识库统计")
def knowledge_stats():
    """获取知识库的统计数据。"""
    try:
        stats = common.knowledge_base.get_stats()
        return jsonify({"success": True, "data": stats}), 200
    except Exception as exc:
        logger.error("获取知识库统计失败: %s", exc)
        return jsonify({"success": False, "message": "获取统计信息失败"}), 500
