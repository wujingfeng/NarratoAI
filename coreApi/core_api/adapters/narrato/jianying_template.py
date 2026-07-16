"""Side-effect-free Jianying schema extracted from the legacy plaintext builder.

This file is byte-synchronized with app/services/jianying_manifest_template.py.
Do not edit one copy without the other.
"""

import base64
import copy
import hashlib
import json
from collections.abc import Mapping, Sequence

DRAFT = '{"canvas_config":{"background":null,"height":360,"ratio":"original","width":640},"color_space":0,"config":{"adjust_max_index":1,"attachment_info":[],"combination_max_index":1,"export_range":null,"extract_audio_last_index":1,"lyrics_recognition_id":"","lyrics_sync":true,"lyrics_taskinfo":[],"maintrack_adsorb":true,"material_save_mode":0,"multi_language_current":"none","multi_language_list":[],"multi_language_main":"none","multi_language_mode":"none","original_sound_last_index":1,"record_audio_last_index":1,"sticker_max_index":1,"subtitle_keywords_config":null,"subtitle_recognition_id":"","subtitle_sync":true,"subtitle_taskinfo":[],"system_font_list":[],"video_mute":false,"zoom_info_params":null},"cover":null,"create_time":0,"draft_type":"video","duration":1000000,"extra_info":null,"fps":30.0,"free_render_index_mode_on":false,"function_assistant_info":{"audio_noise_segid_list":[],"auto_adjust":false,"auto_adjust_fixed":false,"auto_adjust_fixed_value":50.0,"auto_adjust_segid_list":[],"auto_caption":false,"auto_caption_segid_list":[],"auto_caption_template_id":"","caption_opt":false,"caption_opt_segid_list":[],"color_correction":false,"color_correction_fixed":false,"color_correction_fixed_value":50.0,"color_correction_segid_list":[],"deflicker_segid_list":[],"enhance_quality":false,"enhance_quality_fixed":false,"enhance_quality_segid_list":[],"enhance_voice_segid_list":[],"enhande_voice":false,"enhande_voice_fixed":false,"eye_correction":false,"eye_correction_segid_list":[],"fixed_rec_applied":false,"fps":{"den":1,"num":0},"normalize_loudness":false,"normalize_loudness_audio_denoise_segid_list":[],"normalize_loudness_fixed":false,"normalize_loudness_segid_list":[],"retouch":false,"retouch_fixed":false,"retouch_segid_list":[],"smart_rec_applied":false,"smart_segid_list":[],"smooth_slow_motion":false,"smooth_slow_motion_fixed":false,"video_noise_segid_list":[]},"group_container":null,"id":"00000000000000000000000000000000","is_drop_frame_timecode":false,"keyframe_graph_list":[],"keyframes":{"adjusts":[],"audios":[],"effects":[],"filters":[],"handwrites":[],"stickers":[],"texts":[],"videos":[]},"last_modified_platform":{"app_id":3704,"app_source":"lv","app_version":"10.6.0","device_id":"","hard_disk_id":"","mac_address":"","os":"mac","os_version":""},"lyrics_effects":[],"materials":{"ai_translates":[],"audio_balances":[],"audio_effects":[],"audio_fades":[],"audio_pannings":[],"audio_pitch_shifts":[],"audio_track_indexes":[],"audios":[{"ai_music_enter_from":"","ai_music_generate_scene":"","ai_music_type":0,"aigc_history_id":"","aigc_item_id":"","app_id":0,"category_id":"","category_name":"local","check_flag":1,"cloned_model_type":"","copyright_limit_type":"none","duration":1000000,"effect_id":"","formula_id":"","id":"3cefa2e795a54dd19e66b18373ca4e8b","intensifies_path":"","is_ai_clone_tone":false,"is_ai_clone_tone_post":false,"is_text_edit_overdub":false,"is_ugc":false,"local_material_id":"3cefa2e795a54dd19e66b18373ca4e8b","lyric_type":0,"mock_tone_speaker":"","moyin_emotion":"","music_id":"3cefa2e795a54dd19e66b18373ca4e8b","music_source":"","name":"final.wav","path":"##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##/assets/voice/final.wav","pgc_id":"","pgc_name":"","query":"","remote_url":"","request_id":"","resource_id":"","search_id":"","similiar_music_info":null,"sound_separate_type":0,"source_from":"","source_platform":0,"team_id":"","text_id":"","third_resource_id":"","tone_category_id":"","tone_category_name":"","tone_effect_id":"","tone_effect_name":"","tone_emotion_name_key":"","tone_emotion_role":"","tone_emotion_scale":0,"tone_emotion_selection":"","tone_emotion_style":"","tone_platform":"","tone_second_category_id":"","tone_second_category_name":"","tone_speaker":"","tone_type":"","tts_benefit_info":null,"tts_generate_scene":0,"tts_task_id":"","type":"extract_music","unique_id":"","video_id":"","wave_points":[]}],"beats":[],"canvases":[],"chromas":[],"color_curves":[],"common_mask":[],"digital_human_model_dressing":[],"digital_humans":[],"drafts":[],"effects":[],"flowers":[],"green_screens":[],"handwrites":[],"hsl":[],"hsl_curves":[],"images":[],"log_color_wheels":[],"loudnesses":[],"manual_beautys":[],"manual_deformations":[],"material_animations":[],"material_colors":[],"multi_language_refs":[],"placeholder_infos":[],"placeholders":[],"plugin_effects":[],"primary_color_wheels":[],"realtime_denoises":[],"shapes":[],"smart_crops":[],"smart_relights":[],"sound_channel_mappings":[],"speeds":[],"stickers":[],"tail_leaders":[],"text_templates":[],"texts":[{"alignment":1,"check_flag":15,"content":"{\\"styles\\": [{\\"fill\\": {\\"alpha\\": 1.0, \\"content\\": {\\"render_type\\": \\"solid\\", \\"solid\\": {\\"alpha\\": 1.0, \\"color\\": [1.0, 1.0, 1.0]}}}, \\"range\\": [0, 8], \\"size\\": 4.0, \\"bold\\": false, \\"italic\\": false, \\"underline\\": false, \\"strokes\\": [{\\"content\\": {\\"solid\\": {\\"alpha\\": 1.0, \\"color\\": [0.0, 0.0, 0.0]}}, \\"width\\": 0.003}]}], \\"text\\": \\"TEMPLATE\\"}","force_apply_line_max_width":false,"global_alpha":1.0,"id":"9ac9c6cd107446038af96fadf21d99b2","letter_spacing":0.0,"line_feed":1,"line_max_width":0.82,"line_spacing":0.02,"type":"subtitle","typesetting":0}],"time_marks":[],"transitions":[],"video_effects":[],"video_radius":[],"video_shadows":[],"video_strokes":[],"video_trackings":[],"videos":[{"aigc_history_id":"","aigc_item_id":"","aigc_type":"none","audio_fade":null,"beauty_body_auto_preset":null,"beauty_body_preset_id":"","beauty_face_auto_preset":null,"beauty_face_auto_preset_infos":[],"beauty_face_preset_infos":[],"cartoon_path":"","category_id":"","category_name":"local","check_flag":65535,"content_feature_info":null,"corner_pin":null,"create_time":1784234850219328,"crop":{"lower_left_x":0.0,"lower_left_y":1.0,"lower_right_x":1.0,"lower_right_y":1.0,"upper_left_x":0.0,"upper_left_y":0.0,"upper_right_x":1.0,"upper_right_y":0.0},"crop_ratio":"free","crop_scale":1.0,"duration":1000000,"extra_type_option":0,"formula_id":"","freeze":null,"has_audio":true,"has_sound_separated":false,"height":360,"id":"8b96cea42a7d438581aaf55d96fc0a27","intensifies_audio_path":"","intensifies_path":"","is_ai_generate_content":false,"is_copyright":false,"is_set_beauty_mode":false,"is_text_edit_overdub":false,"is_unified_beauty_mode":false,"live_photo_cover_path":"","live_photo_timestamp":0,"local_id":"","local_material_from":0,"local_material_id":"","material_id":"","material_name":"final.mp4","material_url":"","matting":null,"media_path":"","multi_camera_info":null,"object_locked":null,"origin_material_id":"","path":"##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##/assets/video/final.mp4","picture_from":"none","picture_set_category_id":"","picture_set_category_name":"","request_id":"","reverse_intensifies_path":"","reverse_path":"","smart_match_info":null,"smart_motion":null,"source":0,"source_platform":0,"stable":null,"surface_trackings":null,"team_id":"","type":"video","unique_id":"","video_algorithm":null,"video_mask_shadow":null,"video_mask_stroke":null,"width":640}],"vocal_beautifys":[],"vocal_separations":[]},"mutable_config":null,"name":"NarratoAI_TEMPLATE","new_version":"169.0.0","path":"","platform":{"app_id":3704,"app_source":"lv","app_version":"10.6.0","device_id":"","hard_disk_id":"","mac_address":"","os":"mac","os_version":""},"relationships":[],"render_index_track_mode_on":true,"retouch_cover":null,"smart_ads_info":{"draft_url":"","page_from":"","routine":""},"source":"default","static_cover_image_path":"","time_marks":null,"tracks":[{"attribute":0,"flag":0,"id":"50fb03b26c6243f8b70e5d92abc7d9de","is_default_name":true,"name":"Video","segments":[{"caption_info":null,"cartoon":false,"clip":{"alpha":1.0,"flip":{"horizontal":false,"vertical":false},"rotation":0.0,"scale":{"x":1.0,"y":1.0},"transform":{"x":0.0,"y":0.0}},"color_correct_alg_result":"","common_keyframes":[],"desc":"","digital_human_template_group_id":"","enable_adjust":true,"enable_adjust_mask":true,"enable_color_adjust_pro":false,"enable_color_correct_adjust":false,"enable_color_curves":true,"enable_color_match_adjust":false,"enable_color_wheels":true,"enable_hsl":true,"enable_hsl_curves":true,"enable_lut":true,"enable_mask_shadow":false,"enable_mask_stroke":false,"enable_smart_color_adjust":false,"enable_video_mask":true,"extra_material_refs":[],"group_id":"","hdr_settings":{"intensity":1.0,"mode":1,"nits":1000},"id":"fa380afcf52f4410a9099cf30ded8d35","intensifies_audio":false,"is_loop":false,"is_placeholder":false,"is_tone_modify":false,"keyframe_refs":[],"last_nonzero_volume":1.0,"lyric_keyframes":null,"material_id":"8b96cea42a7d438581aaf55d96fc0a27","raw_segment_id":"","render_index":0,"render_timerange":{"duration":0,"start":0},"responsive_layout":{"enable":false,"horizontal_pos_layout":0,"size_layout":0,"target_follow":"","vertical_pos_layout":0},"reverse":false,"source":"segmentsourcenormal","source_timerange":{"duration":1000000,"start":0},"speed":1.0,"state":0,"target_timerange":{"duration":1000000,"start":0},"template_id":"","template_scene":"default","track_attribute":0,"track_render_index":0,"uniform_scale":{"on":true,"value":1.0},"visible":true,"volume":1.0}],"type":"video"},{"attribute":0,"flag":0,"id":"9b249bf885654805872413ecb25ab7ed","is_default_name":true,"name":"Audio","segments":[{"caption_info":null,"cartoon":false,"clip":null,"color_correct_alg_result":"","common_keyframes":[],"desc":"","digital_human_template_group_id":"","enable_adjust":false,"enable_adjust_mask":false,"enable_color_adjust_pro":false,"enable_color_correct_adjust":false,"enable_color_curves":true,"enable_color_match_adjust":false,"enable_color_wheels":true,"enable_hsl":false,"enable_hsl_curves":true,"enable_lut":false,"enable_mask_shadow":false,"enable_mask_stroke":false,"enable_smart_color_adjust":false,"enable_video_mask":true,"extra_material_refs":[],"group_id":"","hdr_settings":null,"id":"addf1c916927444b9e163ca2106939f8","intensifies_audio":false,"is_loop":false,"is_placeholder":false,"is_tone_modify":false,"keyframe_refs":[],"last_nonzero_volume":1.0,"lyric_keyframes":null,"material_id":"3cefa2e795a54dd19e66b18373ca4e8b","raw_segment_id":"","render_index":0,"render_timerange":{"duration":0,"start":0},"responsive_layout":{"enable":false,"horizontal_pos_layout":0,"size_layout":0,"target_follow":"","vertical_pos_layout":0},"reverse":false,"source":"segmentsourcenormal","source_timerange":{"duration":1000000,"start":0},"speed":1.0,"state":0,"target_timerange":{"duration":1000000,"start":0},"template_id":"","template_scene":"default","track_attribute":0,"track_render_index":1,"uniform_scale":null,"visible":true,"volume":1.0}],"type":"audio"},{"attribute":0,"flag":0,"id":"085f444f91e440d0b4e0aeeae8421e6f","is_default_name":false,"name":"字幕轨道","segments":[{"caption_info":null,"cartoon":false,"clip":{"alpha":1.0,"flip":{"horizontal":false,"vertical":false},"rotation":0.0,"scale":{"x":1.0,"y":1.0},"transform":{"x":0.0,"y":-0.8}},"color_correct_alg_result":"","common_keyframes":[],"desc":"","digital_human_template_group_id":"","enable_adjust":false,"enable_adjust_mask":false,"enable_color_adjust_pro":false,"enable_color_correct_adjust":false,"enable_color_curves":true,"enable_color_match_adjust":false,"enable_color_wheels":true,"enable_hsl":false,"enable_hsl_curves":true,"enable_lut":false,"enable_mask_shadow":false,"enable_mask_stroke":false,"enable_smart_color_adjust":false,"enable_video_mask":true,"extra_material_refs":[],"group_id":"","hdr_settings":null,"id":"f535577cac674c498e633014421dc79b","intensifies_audio":false,"is_loop":false,"is_placeholder":false,"is_tone_modify":false,"keyframe_refs":[],"last_nonzero_volume":1.0,"lyric_keyframes":null,"material_id":"9ac9c6cd107446038af96fadf21d99b2","raw_segment_id":"","render_index":15000,"render_timerange":{"duration":0,"start":0},"responsive_layout":{"enable":false,"horizontal_pos_layout":0,"size_layout":0,"target_follow":"","vertical_pos_layout":0},"reverse":false,"source":"segmentsourcenormal","source_timerange":null,"speed":1.0,"state":0,"target_timerange":{"duration":1000000,"start":0},"template_id":"","template_scene":"default","track_attribute":0,"track_render_index":2,"uniform_scale":{"on":true,"value":1.0},"visible":true,"volume":1.0}],"type":"text"}],"uneven_animation_template_info":{"composition":"","content":"","order":"","sub_template_info_list":[]},"update_time":0,"version":360000}'
EMPTY = '{"canvas_config":{"background":null,"height":0,"ratio":"original","width":0},"color_space":-1,"config":{"adjust_max_index":1,"attachment_info":[],"combination_max_index":1,"export_range":null,"extract_audio_last_index":1,"lyrics_recognition_id":"","lyrics_sync":true,"lyrics_taskinfo":[],"maintrack_adsorb":true,"material_save_mode":0,"multi_language_current":"none","multi_language_list":[],"multi_language_main":"none","multi_language_mode":"none","original_sound_last_index":1,"record_audio_last_index":1,"sticker_max_index":1,"subtitle_keywords_config":null,"subtitle_recognition_id":"","subtitle_sync":true,"subtitle_taskinfo":[],"system_font_list":[],"video_mute":false,"zoom_info_params":null},"cover":null,"create_time":0,"draft_type":"video","duration":0,"extra_info":null,"fps":30.0,"free_render_index_mode_on":false,"function_assistant_info":{"audio_noise_segid_list":[],"auto_adjust":false,"auto_adjust_fixed":false,"auto_adjust_fixed_value":50.0,"auto_adjust_segid_list":[],"auto_caption":false,"auto_caption_segid_list":[],"auto_caption_template_id":"","caption_opt":false,"caption_opt_segid_list":[],"color_correction":false,"color_correction_fixed":false,"color_correction_fixed_value":50.0,"color_correction_segid_list":[],"deflicker_segid_list":[],"enhance_quality":false,"enhance_quality_fixed":false,"enhance_quality_segid_list":[],"enhance_voice_segid_list":[],"enhande_voice":false,"enhande_voice_fixed":false,"eye_correction":false,"eye_correction_segid_list":[],"fixed_rec_applied":false,"fps":{"den":1,"num":0},"normalize_loudness":false,"normalize_loudness_audio_denoise_segid_list":[],"normalize_loudness_fixed":false,"normalize_loudness_segid_list":[],"retouch":false,"retouch_fixed":false,"retouch_segid_list":[],"smart_rec_applied":false,"smart_segid_list":[],"smooth_slow_motion":false,"smooth_slow_motion_fixed":false,"video_noise_segid_list":[]},"group_container":null,"id":"00000000000000000000000000000000","is_drop_frame_timecode":false,"keyframe_graph_list":[],"keyframes":{"adjusts":[],"audios":[],"effects":[],"filters":[],"handwrites":[],"stickers":[],"texts":[],"videos":[]},"last_modified_platform":{"app_id":3704,"app_source":"lv","app_version":"10.6.0","device_id":"","hard_disk_id":"","mac_address":"","os":"mac","os_version":""},"lyrics_effects":[],"materials":{"ai_translates":[],"audio_balances":[],"audio_effects":[],"audio_fades":[],"audio_pannings":[],"audio_pitch_shifts":[],"audio_track_indexes":[],"audios":[],"beats":[],"canvases":[],"chromas":[],"color_curves":[],"common_mask":[],"digital_human_model_dressing":[],"digital_humans":[],"drafts":[],"effects":[],"flowers":[],"green_screens":[],"handwrites":[],"hsl":[],"hsl_curves":[],"images":[],"log_color_wheels":[],"loudnesses":[],"manual_beautys":[],"manual_deformations":[],"material_animations":[],"material_colors":[],"multi_language_refs":[],"placeholder_infos":[],"placeholders":[],"plugin_effects":[],"primary_color_wheels":[],"realtime_denoises":[],"shapes":[],"smart_crops":[],"smart_relights":[],"sound_channel_mappings":[],"speeds":[],"stickers":[],"tail_leaders":[],"text_templates":[],"texts":[],"time_marks":[],"transitions":[],"video_effects":[],"video_radius":[],"video_shadows":[],"video_strokes":[],"video_trackings":[],"videos":[],"vocal_beautifys":[],"vocal_separations":[]},"mutable_config":null,"name":"","new_version":"75.0.0","path":"","platform":{"app_id":3704,"app_source":"lv","app_version":"10.6.0","device_id":"","hard_disk_id":"","mac_address":"","os":"mac","os_version":""},"relationships":[],"render_index_track_mode_on":true,"retouch_cover":null,"smart_ads_info":{"draft_url":"","page_from":"","routine":""},"source":"default","static_cover_image_path":"","time_marks":null,"tracks":[],"uneven_animation_template_info":{"composition":"","content":"","order":"","sub_template_info_list":[]},"update_time":0,"version":360000}'
META = '{"cloud_draft_cover":false,"cloud_draft_sync":false,"cloud_package_completed_time":"","draft_cloud_capcut_purchase_info":"","draft_cloud_last_action_download":false,"draft_cloud_package_type":"","draft_cloud_purchase_info":"","draft_cloud_template_id":"","draft_cloud_tutorial_info":"","draft_cloud_videocut_purchase_info":"","draft_cover":"draft_cover.jpg","draft_deeplink_url":"","draft_enterprise_info":{"draft_enterprise_extra":"","draft_enterprise_id":"","draft_enterprise_name":"","enterprise_material":[]},"draft_fold_path":"","draft_id":"00000000-0000-0000-0000-000000000000","draft_is_ae_produce":false,"draft_is_ai_packaging_used":false,"draft_is_ai_shorts":false,"draft_is_ai_translate":false,"draft_is_article_video_draft":false,"draft_is_cloud_temp_draft":false,"draft_is_from_deeplink":"false","draft_is_invisible":false,"draft_is_pippit_draft":false,"draft_is_web_article_video":false,"draft_materials":[{"type":0,"value":[{"ai_group_type":"","create_time":-1,"duration":1000000,"enter_from":0,"extra_info":"final.mp4","file_Path":"##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##/assets/video/final.mp4","height":360,"id":"8b96cea42a7d438581aaf55d96fc0a27","import_time":-1,"import_time_ms":-1,"item_source":1,"md5":"","metetype":"video","roughcut_time_range":{"duration":1000000,"start":0},"sub_time_range":{"duration":-1,"start":-1},"type":0,"width":640},{"ai_group_type":"","create_time":-1,"duration":1000000,"enter_from":0,"extra_info":"final.wav","file_Path":"##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##/assets/voice/final.wav","height":0,"id":"3cefa2e795a54dd19e66b18373ca4e8b","import_time":-1,"import_time_ms":-1,"item_source":1,"md5":"","metetype":"music","roughcut_time_range":{"duration":1000000,"start":0},"sub_time_range":{"duration":-1,"start":-1},"type":0,"width":0}]},{"type":1,"value":[]},{"type":2,"value":[]},{"type":3,"value":[]},{"type":6,"value":[]},{"type":7,"value":[]},{"type":8,"value":[]}],"draft_materials_copied_info":[],"draft_name":"NarratoAI_TEMPLATE","draft_need_rename_folder":false,"draft_new_version":"","draft_removable_storage_device":"","draft_root_path":"","draft_segment_extra_info":[],"draft_timeline_materials_size_":0,"draft_type":"","draft_web_article_video_enter_from":"","tm_draft_cloud_completed":"","tm_draft_cloud_entry_id":-1,"tm_draft_cloud_modified":0,"tm_draft_cloud_parent_entry_id":-1,"tm_draft_cloud_space_id":-1,"tm_draft_cloud_user_id":-1,"tm_draft_create":0,"tm_draft_modified":0,"tm_draft_removed":0,"tm_duration":1000000}'
REFERENCE = '{"reference_lines_config":{"horizontal_lines":[],"is_lock":false,"is_visible":false,"vertical_lines":[]},"safe_area_type":0}'
EDITING = '{"editing_draft":{"ai_remove_filter_words":{"enter_source":"","right_id":""},"ai_shorts_info":{"report_params":"","type":0},"cover_extra_info":{"draft_id":"","position":0,"select_segment_id":"","select_segment_source_start":0,"select_segment_target_start":0,"type":1},"crop_info_extra":{"crop_mirror_type":0,"crop_rotate":0,"crop_rotate_total":0},"digital_human_template_to_video_info":{"has_upload_material":false,"template_type":0},"draft_used_recommend_function":"","edit_type":0,"eye_correct_enabled_multi_face_time":0,"has_adjusted_render_layer":false,"image_ai_chat_info":{"before_chat_edit":false,"draft_modify_time":0,"generate_type":"","keyword_content":"","keyword_type":"","message_id":"","model_name":"","need_restore":false,"picture_id":"","prompt_content":"","prompt_from":"","sugs_info":[]},"is_open_expand_player":false,"is_template_text_ai_generate":false,"is_use_adjust":false,"is_use_ai_expand":false,"is_use_ai_remove":false,"is_use_ai_video":false,"is_use_audio_separation":false,"is_use_chroma_key":false,"is_use_curve_speed":false,"is_use_digital_human":false,"is_use_edit_multi_camera":false,"is_use_lip_sync":false,"is_use_lock_object":false,"is_use_loudness_unify":false,"is_use_noise_reduction":false,"is_use_one_click_beauty":false,"is_use_one_click_ultra_hd":false,"is_use_retouch_face":false,"is_use_smart_adjust_color":false,"is_use_smart_body_beautify":false,"is_use_smart_motion":false,"is_use_subtitle_recognition":false,"is_use_text_to_audio":false,"material_edit_session":{"material_edit_info":[],"session_id":"","session_time":0},"paste_segment_list":[],"profile_entrance_type":"","publish_enter_from":"","publish_type":"","single_function_type":0,"text_convert_case_types":[],"version":"1.0.0","video_recording_create_draft":""}}'
VIRTUAL = '{"draft_materials":[],"draft_virtual_store":[{"type":0,"value":[{"creation_time":0,"display_name":"","filter_type":0,"id":"","import_time":0,"import_time_us":0,"sort_sub_type":0,"sort_type":0,"subdraft_filter_type":0}]},{"type":1,"value":[{"child_id":"8b96cea42a7d438581aaf55d96fc0a27","parent_id":""},{"child_id":"3cefa2e795a54dd19e66b18373ca4e8b","parent_id":""}]},{"type":2,"value":[]}]}'
COVER = "/9j/2wBDAP/////////////////////////////////////////////////////////////////////////////AAAsIAAEAAQEBEQD/xAAUAAEAAAAAAAAAAAAAAAAAAAAB/8QAFBABAAAAAAAAAAAAAAAAAAAAAf/aAAgBAQAAPwB//9k="


MICROSECONDS = 1_000_000
DRAFT_PATH_PLACEHOLDER = (
    "##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##"
)


def _id(snapshot_id: str, label: str) -> str:
    return hashlib.sha256(f"{snapshot_id}:{label}".encode()).hexdigest()[:32]


def _draft_uuid(value: str) -> str:
    return "-".join(
        (value[:8], value[8:12], value[12:16], value[16:20], value[20:])
    ).upper()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def build_jianying_template_files(
    snapshot_id: str,
    timeline: Sequence[Mapping[str, object]],
    resource_paths: Mapping[str, str],
    video_metadata: Mapping[str, object],
) -> dict[str, str | bytes]:
    """Build a complete plaintext Jianying draft from immutable render metadata."""
    name = f"NarratoAI_{snapshot_id}"
    draft_id = _id(snapshot_id, "draft")
    width = int(video_metadata["width"])
    height = int(video_metadata["height"])
    duration_us = int(float(video_metadata["duration"]) * MICROSECONDS)
    video_id = _id(snapshot_id, "video")
    audio_id = _id(snapshot_id, "audio")

    draft = json.loads(DRAFT)
    draft.update({"id": draft_id, "name": name, "duration": duration_us})
    draft["canvas_config"].update({"width": width, "height": height})

    video = draft["materials"]["videos"][0]
    video.update(
        {
            "id": video_id,
            "local_material_id": video_id,
            "path": f"{DRAFT_PATH_PLACEHOLDER}/{resource_paths['video']}",
            "material_name": resource_paths["video"].rsplit("/", 1)[-1],
            "duration": duration_us,
            "width": width,
            "height": height,
        }
    )
    audio = draft["materials"]["audios"][0]
    audio.update(
        {
            "id": audio_id,
            "local_material_id": audio_id,
            "music_id": audio_id,
            "path": f"{DRAFT_PATH_PLACEHOLDER}/{resource_paths['voice']}",
            "name": resource_paths["voice"].rsplit("/", 1)[-1],
            "duration": duration_us,
        }
    )

    video_track, audio_track, text_track = draft["tracks"]
    video_track["id"] = _id(snapshot_id, "video-track")
    audio_track["id"] = _id(snapshot_id, "audio-track")
    text_track["id"] = _id(snapshot_id, "text-track")
    video_segment = video_track["segments"][0]
    video_segment.update(
        {"id": _id(snapshot_id, "video-segment"), "material_id": video_id}
    )
    video_segment["source_timerange"] = {"start": 0, "duration": duration_us}
    video_segment["target_timerange"] = {"start": 0, "duration": duration_us}
    audio_segment = audio_track["segments"][0]
    audio_segment.update(
        {"id": _id(snapshot_id, "audio-segment"), "material_id": audio_id}
    )
    audio_segment["source_timerange"] = {"start": 0, "duration": duration_us}
    audio_segment["target_timerange"] = {"start": 0, "duration": duration_us}

    text_prototype = draft["materials"]["texts"][0]
    text_segment_prototype = text_track["segments"][0]
    texts = []
    text_segments = []
    for index, item in enumerate(timeline):
        material = copy.deepcopy(text_prototype)
        material_id = _id(snapshot_id, f"text-{index}")
        text = str(item["narration"])
        content = json.loads(material["content"])
        content["text"] = text
        for style in content.get("styles", []):
            style["range"] = [0, len(text)]
        material.update({"id": material_id, "content": _json(content)})
        segment = copy.deepcopy(text_segment_prototype)
        start_us = int(float(item["start"]) * MICROSECONDS)
        cue_duration = int((float(item["end"]) - float(item["start"])) * MICROSECONDS)
        segment.update(
            {
                "id": _id(snapshot_id, f"text-segment-{index}"),
                "material_id": material_id,
            }
        )
        segment["target_timerange"] = {"start": start_us, "duration": cue_duration}
        texts.append(material)
        text_segments.append(segment)
    draft["materials"]["texts"] = texts
    text_track["segments"] = text_segments

    empty = json.loads(EMPTY)
    empty["id"] = draft_id
    meta = json.loads(META)
    meta.update(
        {
            "draft_id": _draft_uuid(draft_id),
            "draft_name": name,
            "tm_duration": duration_us,
        }
    )
    indexes = meta["draft_materials"][0]["value"]
    indexes[0].update(
        {
            "duration": duration_us,
            "extra_info": video["material_name"],
            "file_Path": video["path"],
            "height": height,
            "id": video_id,
            "width": width,
            "roughcut_time_range": {"duration": duration_us, "start": 0},
        }
    )
    indexes[1].update(
        {
            "duration": duration_us,
            "extra_info": audio["name"],
            "file_Path": audio["path"],
            "id": audio_id,
            "roughcut_time_range": {"duration": duration_us, "start": 0},
        }
    )
    virtual = json.loads(VIRTUAL)
    virtual["draft_virtual_store"][1]["value"] = [
        {"child_id": video_id, "parent_id": ""},
        {"child_id": audio_id, "parent_id": ""},
    ]
    script_attachment = {
        "narrato_resources": {
            "subtitle": resource_paths["subtitle"],
            "timeline": resource_paths["timeline"],
        }
    }
    return {
        "draft_info.json": _json(draft),
        "template-2.tmp": _json(draft),
        "template.tmp": _json(empty),
        "draft_meta_info.json": _json(meta),
        "draft_settings": "[General]\ncloud_last_modify_platform=\ndraft_create_time=0\ndraft_last_edit_time=0\nreal_edit_keys=1\nreal_edit_seconds=0\n",
        "draft_cover.jpg": base64.b64decode(COVER),
        "common_attachment/attachment_pc_timeline.json": REFERENCE,
        "common_attachment/attachment_action_scene.json": "{}",
        "common_attachment/attachment_script_video.json": _json(script_attachment),
        "common_attachment/attachment_gen_ai_info.json": "{}",
        "attachment_editing.json": EDITING,
        "draft_virtual_store.json": _json(virtual),
        "draft_agency_config.json": _json(
            {
                "is_auto_agency_enabled": False,
                "is_auto_agency_popup": False,
                "is_single_agency_mode": False,
                "marterials": None,
                "use_converter": False,
                "video_resolution": height,
            }
        ),
        "draft_biz_config.json": "",
        "performance_opt_info.json": _json(
            {"manual_cancle_precombine_segs": None, "need_auto_precombine_segs": None}
        ),
        "timeline_layout.json": _json(
            {
                "activeTimeline": draft_id,
                "dockItems": [
                    {
                        "dockIndex": 0,
                        "ratio": 1,
                        "timelineIds": [draft_id],
                        "timelineNames": ["时间线01"],
                    }
                ],
                "layoutOrientation": 1,
            }
        ),
    }
