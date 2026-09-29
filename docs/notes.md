
[a@archlinux ~]$ uname -r
pacman -Q webkit2gtk-4.1 mesa vulkan-intel chromium
plasmashell --version
echo "$XDG_SESSION_TYPE"
kscreen-doctor -o | sed 's/\x1b\[[0-9;]*m//g' | grep -E 'Output|Modes|Geometry|Scale'
7.2.7-arch1-1
webkit2gtk-4.1 2.52.6-1
mesa 1:26.2.3-1
vulkan-intel 1:26.2.3-1
chromium 153.0.8010.52-1
plasmashell 6.7.5
wayland
Output: 1 eDP-1 0a914977-cee1-4719-94f8-7e08c7703c49
        Modes:  1:2560x1600@144.00*!  2:2560x1600@60.00  3:1600x1200@59.87  4:1600x1200@143.89  5:1280x1024@59.90  6:1280x1024@143.79  7:1024x768@59.92  8:1024x768@143.87  9:1920x1200@59.88  10:1920x1200@143.89  11:1280x800@59.81  12:1280x800@143.84  13:2560x1440@59.96  14:2560x1440@143.91  15:1920x1080@59.96  16:1920x1080@143.88  17:1600x900@59.95  18:1600x900@143.93  19:1368x768@59.88  20:1368x768@143.77  21:1280x720@59.85  22:1280x720@143.85 
        Geometry: 0,0 2048x1280
        Scale: 1.25













result ftom /usr/lib/webkit2gtk-4.1/MiniBrowser webkit://gpu:

{
    "Version Information": {
        "WebKit version": "WebKitGTK 2.52.6 (tarball)",
        "Operating system": "Linux 7.2.7-arch1-1 #1 SMP PREEMPT_DYNAMIC Mon, 21 Sep 2026 18:51:14 +0000 x86_64",
        "Desktop": "KDE",
        "GStreamer version": "1.28.6 (build) GStreamer 1.28.7 (runtime)",
        "GTK version": "3.24.52 (build) 3.24.52 (runtime)"
    },
    "Display Information": {
        "Identifier": "1",
        "Type": "Wayland",
        "Screen geometry": "0,0 2048x1280",
        "Screen work area": "0,0 2048x1280",
        "Device scale": "2",
        "Depth": "32",
        "Bits per color component": "8",
        "Font Scaling DPI": "96",
        "Screen DPI": "150.9030268941262",
        "VBlank type": "Timer",
        "VBlank refresh rate": "60Hz",
        "DRM Primary Node": "/dev/dri/card1",
        "DRM Render Node": "/dev/dri/renderD128"
    },
    "View Information": {
        "Size": "1024x732",
        "State": "in window, visible, focused, active"
    },
    "Hardware Acceleration Information": {
        "Policy": "always",
        "WebGL enabled": "Yes",
        "2D canvas": "Accelerated",
        "API": "OpenGL (libepoxy)",
        "Renderer": "DMABuf (Supported buffers: Hardware, Shared Memory)",
        "Preferred buffer formats": [
            {
                "Usage": "Rendering",
                "Device": "/dev/dri/renderD128",
                "Formats": [
                    "XR24 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_MC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
                    "XB24 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_MC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
                    "AR24 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_MC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
                    "AB24 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_MC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
                    "RG16 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
                    "XR30 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
                    "XB30 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
                    "AR30 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
                    "AB30 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
                    "XB4H (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
                    "AB4H (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)"
                ]
            }
        ],
        "Buffer format": "DMA-BUF: XR24 (INTEL_Y_TILED_GEN12_RC_CCS_CC) [Rendering]",
        "Native interface": "EGL",
        "GL_RENDERER": "Mesa Intel(R) Iris(R) Xe Graphics (RPL-P)",
        "GL_VENDOR": "Intel",
        "GL_VERSION": "4.6 (Core Profile) Mesa 26.2.3-arch1.1",
        "GL_SHADING_LANGUAGE_VERSION": "4.60",
        "GL_EXTENSIONS": "GL_3DFX_texture_compression_FXT1 GL_AMD_conservative_depth GL_AMD_depth_clamp_separate GL_AMD_draw_buffers_blend GL_AMD_gpu_shader_int64 GL_AMD_multi_draw_indirect GL_AMD_performance_monitor GL_AMD_pinned_memory GL_AMD_query_buffer_object GL_AMD_seamless_cubemap_per_texture GL_AMD_shader_stencil_export GL_AMD_shader_trinary_minmax GL_AMD_texture_texture4 GL_AMD_vertex_shader_layer GL_AMD_vertex_shader_viewport_index GL_ANGLE_texture_compression_dxt3 GL_ANGLE_texture_compression_dxt5 GL_ARB_ES2_compatibility GL_ARB_ES3_1_compatibility GL_ARB_ES3_2_compatibility GL_ARB_ES3_compatibility GL_ARB_arrays_of_arrays GL_ARB_base_instance GL_ARB_blend_func_extended GL_ARB_buffer_storage GL_ARB_clear_buffer_object GL_ARB_clear_texture GL_ARB_clip_control GL_ARB_compressed_texture_pixel_storage GL_ARB_compute_shader GL_ARB_compute_variable_group_size GL_ARB_conditional_render_inverted GL_ARB_conservative_depth GL_ARB_copy_buffer GL_ARB_copy_image GL_ARB_cull_distance GL_ARB_debug_output GL_ARB_depth_buffer_float GL_ARB_depth_clamp GL_ARB_derivative_control GL_ARB_direct_state_access GL_ARB_draw_buffers GL_ARB_draw_buffers_blend GL_ARB_draw_elements_base_vertex GL_ARB_draw_indirect GL_ARB_draw_instanced GL_ARB_enhanced_layouts GL_ARB_explicit_attrib_location GL_ARB_explicit_uniform_location GL_ARB_fragment_coord_conventions GL_ARB_fragment_layer_viewport GL_ARB_fragment_shader GL_ARB_fragment_shader_interlock GL_ARB_framebuffer_no_attachments GL_ARB_framebuffer_object GL_ARB_framebuffer_sRGB GL_ARB_get_program_binary GL_ARB_get_texture_sub_image GL_ARB_gl_spirv GL_ARB_gpu_shader5 GL_ARB_gpu_shader_fp64 GL_ARB_gpu_shader_int64 GL_ARB_half_float_pixel GL_ARB_half_float_vertex GL_ARB_indirect_parameters GL_ARB_instanced_arrays GL_ARB_internalformat_query GL_ARB_internalformat_query2 GL_ARB_invalidate_subdata GL_ARB_map_buffer_alignment GL_ARB_map_buffer_range GL_ARB_multi_bind GL_ARB_multi_draw_indirect GL_ARB_occlusion_query2 GL_ARB_parallel_shader_compile GL_ARB_pipeline_statistics_query GL_ARB_pixel_buffer_object GL_ARB_point_sprite GL_ARB_polygon_offset_clamp GL_ARB_post_depth_coverage GL_ARB_program_interface_query GL_ARB_provoking_vertex GL_ARB_query_buffer_object GL_ARB_robust_buffer_access_behavior GL_ARB_robustness GL_ARB_sample_shading GL_ARB_sampler_objects GL_ARB_seamless_cube_map GL_ARB_seamless_cubemap_per_texture GL_ARB_separate_shader_objects GL_ARB_shader_atomic_counter_ops GL_ARB_shader_atomic_counters GL_ARB_shader_ballot GL_ARB_shader_bit_encoding GL_ARB_shader_clock GL_ARB_shader_draw_parameters GL_ARB_shader_group_vote GL_ARB_shader_image_load_store GL_ARB_shader_image_size GL_ARB_shader_objects GL_ARB_shader_precision GL_ARB_shader_stencil_export GL_ARB_shader_storage_buffer_object GL_ARB_shader_subroutine GL_ARB_shader_texture_image_samples GL_ARB_shader_texture_lod GL_ARB_shader_viewport_layer_array GL_ARB_shading_language_420pack GL_ARB_shading_language_include GL_ARB_shading_language_packing GL_ARB_spirv_extensions GL_ARB_stencil_texturing GL_ARB_sync GL_ARB_tessellation_shader GL_ARB_texture_barrier GL_ARB_texture_border_clamp GL_ARB_texture_buffer_object GL_ARB_texture_buffer_object_rgb32 GL_ARB_texture_buffer_range GL_ARB_texture_compression_bptc GL_ARB_texture_compression_rgtc GL_ARB_texture_cube_map_array GL_ARB_texture_filter_anisotropic GL_ARB_texture_filter_minmax GL_ARB_texture_float GL_ARB_texture_gather GL_ARB_texture_mirror_clamp_to_edge GL_ARB_texture_multisample GL_ARB_texture_non_power_of_two GL_ARB_texture_query_levels GL_ARB_texture_query_lod GL_ARB_texture_rectangle GL_ARB_texture_rg GL_ARB_texture_rgb10_a2ui GL_ARB_texture_stencil8 GL_ARB_texture_storage GL_ARB_texture_storage_multisample GL_ARB_texture_swizzle GL_ARB_texture_view GL_ARB_timer_query GL_ARB_transform_feedback2 GL_ARB_transform_feedback3 GL_ARB_transform_feedback_instanced GL_ARB_transform_feedback_overflow_query GL_ARB_uniform_buffer_object GL_ARB_vertex_array_bgra GL_ARB_vertex_array_object GL_ARB_vertex_attrib_64bit GL_ARB_vertex_attrib_binding GL_ARB_vertex_buffer_object GL_ARB_vertex_shader GL_ARB_vertex_type_10f_11f_11f_rev GL_ARB_vertex_type_2_10_10_10_rev GL_ARB_viewport_array GL_ATI_blend_equation_separate GL_ATI_texture_float GL_EXT_EGL_image_storage GL_EXT_EGL_image_storage_compression GL_EXT_EGL_sync GL_EXT_abgr GL_EXT_blend_equation_separate GL_EXT_debug_label GL_EXT_demote_to_helper_invocation GL_EXT_depth_bounds_test GL_EXT_draw_buffers2 GL_EXT_draw_instanced GL_EXT_framebuffer_blit GL_EXT_framebuffer_multisample GL_EXT_framebuffer_multisample_blit_scaled GL_EXT_framebuffer_object GL_EXT_framebuffer_sRGB GL_EXT_memory_object GL_EXT_memory_object_fd GL_EXT_packed_depth_stencil GL_EXT_packed_float GL_EXT_pixel_buffer_object GL_EXT_polygon_offset_clamp GL_EXT_provoking_vertex GL_EXT_semaphore GL_EXT_semaphore_fd GL_EXT_shader_clock GL_EXT_shader_framebuffer_fetch GL_EXT_shader_framebuffer_fetch_non_coherent GL_EXT_shader_integer_mix GL_EXT_shader_samples_identical GL_EXT_texture_array GL_EXT_texture_compression_dxt1 GL_EXT_texture_compression_rgtc GL_EXT_texture_compression_s3tc GL_EXT_texture_filter_anisotropic GL_EXT_texture_integer GL_EXT_texture_sRGB GL_EXT_texture_sRGB_R8 GL_EXT_texture_sRGB_decode GL_EXT_texture_shadow_lod GL_EXT_texture_shared_exponent GL_EXT_texture_snorm GL_EXT_texture_storage GL_EXT_texture_swizzle GL_EXT_timer_query GL_EXT_transform_feedback GL_EXT_vertex_array_bgra GL_EXT_vertex_attrib_64bit GL_IBM_multimode_draw_arrays GL_INTEL_blackhole_render GL_INTEL_conservative_rasterization GL_INTEL_performance_query GL_INTEL_shader_atomic_float_minmax GL_INTEL_shader_integer_functions2 GL_KHR_blend_equation_advanced GL_KHR_blend_equation_advanced_coherent GL_KHR_context_flush_control GL_KHR_debug GL_KHR_no_error GL_KHR_parallel_shader_compile GL_KHR_robust_buffer_access_behavior GL_KHR_robustness GL_KHR_shader_subgroup GL_KHR_texture_compression_astc_ldr GL_KHR_texture_compression_astc_sliced_3d GL_MESA_framebuffer_flip_y GL_MESA_pack_invert GL_MESA_shader_integer_functions GL_MESA_texture_const_bandwidth GL_MESA_texture_signed_rgba GL_NV_alpha_to_coverage_dither_control GL_NV_compute_shader_derivatives GL_NV_conditional_render GL_NV_copy_image GL_NV_depth_clamp GL_NV_fragment_shader_interlock GL_NV_packed_depth_stencil GL_NV_texture_barrier GL_OES_EGL_image GL_S3_s3tc",
        "EGL_VERSION": "1.5",
        "EGL_VENDOR": "Mesa Project",
        "EGL_EXTENSIONS": "EGL_EXT_platform_base EGL_EXT_device_base EGL_EXT_device_query EGL_EXT_device_enumeration EGL_KHR_client_get_all_proc_addresses EGL_EXT_client_extensions EGL_KHR_debug EGL_KHR_platform_x11 EGL_EXT_platform_x11 EGL_EXT_platform_device EGL_MESA_platform_surfaceless EGL_EXT_explicit_device EGL_KHR_platform_wayland EGL_EXT_platform_wayland EGL_KHR_platform_gbm EGL_MESA_platform_gbm EGL_EXT_platform_xcb EGL_ANDROID_blob_cache EGL_ANDROID_native_fence_sync EGL_EXT_buffer_age EGL_EXT_config_select_group EGL_EXT_create_context_robustness EGL_EXT_image_dma_buf_import EGL_EXT_image_dma_buf_import_modifiers EGL_EXT_present_opaque EGL_EXT_protected_content EGL_EXT_query_reset_notification_strategy EGL_EXT_surface_compression EGL_EXT_swap_buffers_with_damage EGL_IMG_context_priority EGL_KHR_cl_event2 EGL_KHR_config_attribs EGL_KHR_context_flush_control EGL_KHR_create_context EGL_KHR_create_context_no_error EGL_KHR_fence_sync EGL_KHR_get_all_proc_addresses EGL_KHR_gl_colorspace EGL_KHR_gl_renderbuffer_image EGL_KHR_gl_texture_2D_image EGL_KHR_gl_texture_3D_image EGL_KHR_gl_texture_cubemap_image EGL_KHR_image_base EGL_KHR_no_config_context EGL_KHR_partial_update EGL_KHR_reusable_sync EGL_KHR_surfaceless_context EGL_KHR_swap_buffers_with_damage EGL_EXT_pixel_format_float EGL_KHR_wait_sync EGL_MESA_configless_context EGL_MESA_gl_interop EGL_MESA_image_dma_buf_export EGL_MESA_query_driver EGL_MESA_x11_native_visual_id "
    },
    "Hardware Acceleration Information (Render process)": {
        "Platform": "GBM",
        "DRM version": "i915 (Intel Graphics) 1.6.0. 0",
        "Threaded rendering": "GPU (2 threads)",
        "MSAA": "8 samples",
        "Supported buffers": [
            "XR24 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_MC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
            "XB24 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_MC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
            "AR24 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_MC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
            "AB24 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_MC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
            "RG16 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
            "XR30 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
            "XB30 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
            "AR30 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
            "AB30 (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
            "XB4H (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)",
            "AB4H (NONE_LINEAR, INTEL_X_TILED, INTEL_Y_TILED, INTEL_Y_TILED_GEN12_RC_CCS, INTEL_Y_TILED_GEN12_RC_CCS_CC)"
        ],
        "GL_RENDERER": "Mesa Intel(R) Iris(R) Xe Graphics (RPL-P)",
        "GL_VENDOR": "Intel",
        "GL_VERSION": "OpenGL ES 3.2 Mesa 26.2.3-arch1.1",
        "GL_SHADING_LANGUAGE_VERSION": "OpenGL ES GLSL ES 3.20",
        "GL_EXTENSIONS": "GL_EXT_blend_minmax GL_EXT_multi_draw_arrays GL_EXT_texture_filter_anisotropic GL_EXT_texture_compression_s3tc GL_EXT_texture_compression_dxt1 GL_EXT_texture_compression_rgtc GL_EXT_texture_format_BGRA8888 GL_OES_compressed_ETC1_RGB8_texture GL_OES_depth24 GL_OES_element_index_uint GL_OES_fbo_render_mipmap GL_OES_mapbuffer GL_OES_rgb8_rgba8 GL_OES_standard_derivatives GL_OES_stencil8 GL_OES_texture_3D GL_OES_texture_float GL_OES_texture_float_linear GL_OES_texture_half_float GL_OES_texture_half_float_linear GL_OES_texture_npot GL_OES_vertex_half_float GL_EXT_draw_instanced GL_EXT_texture_sRGB_decode GL_OES_EGL_image GL_OES_depth_texture GL_AMD_performance_monitor GL_OES_packed_depth_stencil GL_EXT_texture_type_2_10_10_10_REV GL_NV_conditional_render GL_OES_get_program_binary GL_APPLE_texture_max_level GL_EXT_discard_framebuffer GL_EXT_read_format_bgra GL_EXT_texture_storage GL_NV_pack_subimage GL_NV_texture_barrier GL_EXT_frag_depth GL_NV_fbo_color_attachments GL_OES_EGL_image_external GL_OES_EGL_sync GL_OES_vertex_array_object GL_OES_viewport_array GL_ANGLE_pack_reverse_row_order GL_ANGLE_texture_compression_dxt3 GL_ANGLE_texture_compression_dxt5 GL_EXT_occlusion_query_boolean GL_EXT_robustness GL_EXT_sRGB GL_EXT_texture_rg GL_EXT_unpack_subimage GL_NV_draw_buffers GL_NV_read_buffer GL_NV_read_depth GL_NV_read_depth_stencil GL_NV_read_stencil GL_APPLE_sync GL_EXT_draw_buffers GL_EXT_instanced_arrays GL_EXT_map_buffer_range GL_EXT_shadow_samplers GL_KHR_debug GL_KHR_robustness GL_KHR_texture_compression_astc_ldr GL_NV_generate_mipmap_sRGB GL_NV_pixel_buffer_object GL_OES_depth_texture_cube_map GL_OES_required_internalformat GL_OES_surfaceless_context GL_EXT_color_buffer_float GL_EXT_debug_label GL_EXT_sRGB_write_control GL_EXT_separate_shader_objects GL_EXT_shader_framebuffer_fetch GL_EXT_shader_group_vote GL_EXT_shader_implicit_conversions GL_EXT_shader_integer_mix GL_EXT_tessellation_point_size GL_EXT_tessellation_shader GL_INTEL_conservative_rasterization GL_INTEL_performance_query GL_ANDROID_extension_pack_es31a GL_EXT_base_instance GL_EXT_compressed_ETC1_RGB8_sub_texture GL_EXT_copy_image GL_EXT_draw_buffers_indexed GL_EXT_draw_elements_base_vertex GL_EXT_gpu_shader5 GL_EXT_multi_draw_indirect GL_EXT_polygon_offset_clamp GL_EXT_primitive_bounding_box GL_EXT_render_snorm GL_EXT_shader_io_blocks GL_EXT_texture_border_clamp GL_EXT_texture_buffer GL_EXT_texture_cube_map_array GL_EXT_texture_norm16 GL_EXT_texture_view GL_KHR_blend_equation_advanced GL_KHR_blend_equation_advanced_coherent GL_KHR_context_flush_control GL_KHR_robust_buffer_access_behavior GL_NV_image_formats GL_NV_shader_noperspective_interpolation GL_OES_copy_image GL_OES_draw_buffers_indexed GL_OES_draw_elements_base_vertex GL_OES_gpu_shader5 GL_OES_primitive_bounding_box GL_OES_sample_shading GL_OES_sample_variables GL_OES_shader_io_blocks GL_OES_shader_multisample_interpolation GL_OES_tessellation_point_size GL_OES_tessellation_shader GL_OES_texture_border_clamp GL_OES_texture_buffer GL_OES_texture_cube_map_array GL_OES_texture_stencil8 GL_OES_texture_storage_multisample_2d_array GL_OES_texture_view GL_EXT_blend_func_extended GL_EXT_buffer_storage GL_EXT_float_blend GL_EXT_geometry_point_size GL_EXT_geometry_shader GL_EXT_shader_samples_identical GL_EXT_texture_sRGB_R8 GL_KHR_no_error GL_KHR_texture_compression_astc_sliced_3d GL_NV_fragment_shader_interlock GL_OES_EGL_image_external_essl3 GL_OES_geometry_point_size GL_OES_geometry_shader GL_OES_shader_image_atomic GL_EXT_clear_texture GL_EXT_clip_cull_distance GL_EXT_conservative_depth GL_EXT_disjoint_timer_query GL_EXT_texture_compression_s3tc_srgb GL_MESA_shader_integer_functions GL_EXT_clip_control GL_EXT_color_buffer_half_float GL_EXT_memory_object GL_EXT_memory_object_fd GL_EXT_protected_textures GL_EXT_semaphore GL_EXT_semaphore_fd GL_EXT_texture_compression_bptc GL_EXT_texture_mirror_clamp_to_edge GL_KHR_parallel_shader_compile GL_NV_alpha_to_coverage_dither_control GL_EXT_EGL_image_storage GL_EXT_shader_framebuffer_fetch_non_coherent GL_EXT_texture_shadow_lod GL_INTEL_blackhole_render GL_MESA_framebuffer_flip_y GL_NV_compute_shader_derivatives GL_EXT_demote_to_helper_invocation GL_EXT_depth_clamp GL_EXT_texture_query_lod GL_KHR_shader_subgroup GL_MESA_sampler_objects GL_EXT_EGL_image_storage_compression GL_EXT_texture_storage_compression GL_MESA_bgra GL_MESA_texture_const_bandwidth GL_EXT_shader_clock ",
        "EGL_VERSION": "1.5",
        "EGL_VENDOR": "Mesa Project",
        "EGL_EXTENSIONS": "EGL_EXT_platform_base EGL_EXT_device_base EGL_EXT_device_query EGL_EXT_device_enumeration EGL_KHR_client_get_all_proc_addresses EGL_EXT_client_extensions EGL_KHR_debug EGL_KHR_platform_x11 EGL_EXT_platform_x11 EGL_EXT_platform_device EGL_MESA_platform_surfaceless EGL_EXT_explicit_device EGL_KHR_platform_wayland EGL_EXT_platform_wayland EGL_KHR_platform_gbm EGL_MESA_platform_gbm EGL_EXT_platform_xcb EGL_ANDROID_blob_cache EGL_ANDROID_native_fence_sync EGL_EXT_buffer_age EGL_EXT_config_select_group EGL_EXT_create_context_robustness EGL_EXT_image_dma_buf_import EGL_EXT_image_dma_buf_import_modifiers EGL_EXT_protected_content EGL_EXT_query_reset_notification_strategy EGL_EXT_surface_compression EGL_IMG_context_priority EGL_KHR_cl_event2 EGL_KHR_config_attribs EGL_KHR_context_flush_control EGL_KHR_create_context EGL_KHR_create_context_no_error EGL_KHR_fence_sync EGL_KHR_get_all_proc_addresses EGL_KHR_gl_colorspace EGL_KHR_gl_renderbuffer_image EGL_KHR_gl_texture_2D_image EGL_KHR_gl_texture_3D_image EGL_KHR_gl_texture_cubemap_image EGL_KHR_image EGL_KHR_image_base EGL_KHR_image_pixmap EGL_KHR_no_config_context EGL_KHR_partial_update EGL_KHR_reusable_sync EGL_KHR_surfaceless_context EGL_EXT_pixel_format_float EGL_KHR_wait_sync EGL_MESA_configless_context EGL_MESA_gl_interop EGL_MESA_image_dma_buf_export EGL_MESA_query_driver EGL_MESA_x11_native_visual_id "
    }
}


from tauri diagnotics:

{
  "measuredAt": "2026-09-29T03:09:56.746Z",
  "buildMode": "development",
  "renderer": "Apple GPU",
  "vendor": "Apple Inc.",
  "rendererUnmasked": false,
  "webglVersion": "WebGL 2.0",
  "antialias": true,
  "userAgent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/60.5 Safari/605.1.15",
  "isTauri": true,
  "tauriVersion": "2.11.5",
  "viewport": {
    "width": 1644,
    "height": 910
  },
  "canvasCss": {
    "width": 1644,
    "height": 910
  },
  "screen": {
    "width": 2048,
    "height": 1280
  },
  "devicePixelRatio": 2,
  "drawingBuffer": {
    "width": 2466,
    "height": 1365
  },
  "particleCount": 12000,
  "configuredParticleCount": 12000,
  "qualityTier": "medium",
  "maxPixelRatio": 1.5,
  "sceneState": "home",
  "render": {
    "calls": 3,
    "triangles": 28854,
    "points": 12000,
    "lines": 1989,
    "programs": 3,
    "geometries": 3,
    "textures": 0
  },
  "frames": 240,
  "mean_ms": 32.54,
  "p50_ms": 32,
  "p95_ms": 33,
  "max_ms": 117,
  "implied_fps": 31.25,
  "longFrames": 1,
  "firstFrameAfterLoad_ms": 940,
  "startupWorstFrame_ms": 114,
  "interrupted": false,
  "visibility": "visible"
}

diagnotics II:

{
  "measuredAt": "2026-09-29T03:11:41.317Z",
  "buildMode": "development",
  "renderer": "Apple GPU",
  "vendor": "Apple Inc.",
  "rendererUnmasked": false,
  "webglVersion": "WebGL 2.0",
  "antialias": true,
  "userAgent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/60.5 Safari/605.1.15",
  "isTauri": true,
  "tauriVersion": "2.11.5",
  "viewport": {
    "width": 1644,
    "height": 910
  },
  "canvasCss": {
    "width": 1644,
    "height": 910
  },
  "screen": {
    "width": 2048,
    "height": 1280
  },
  "devicePixelRatio": 2,
  "drawingBuffer": {
    "width": 2466,
    "height": 1365
  },
  "particleCount": 12000,
  "configuredParticleCount": 12000,
  "qualityTier": "medium",
  "maxPixelRatio": 1.5,
  "sceneState": "home",
  "render": {
    "calls": 3,
    "triangles": 28854,
    "points": 12000,
    "lines": 1989,
    "programs": 3,
    "geometries": 3,
    "textures": 0
  },
  "frames": 240,
  "mean_ms": 32.37,
  "p50_ms": 32,
  "p95_ms": 33,
  "max_ms": 51,
  "implied_fps": 31.25,
  "longFrames": 0,
  "firstFrameAfterLoad_ms": 940,
  "startupWorstFrame_ms": 114,
  "interrupted": false,
  "visibility": "visible"
}


result from await command ,konsole:
[Info] Object

antialias: true

buildMode: "development"

canvasCss: {width: 1644, height: 610}

configuredParticleCount: 12000

devicePixelRatio: 2

drawingBuffer: {width: 2466, height: 915}

firstFrameAfterLoad_ms: 940

frames: 240

implied_fps: 31.25

interrupted: false

isTauri: true

longFrames: 2

maxPixelRatio: 1.5

max_ms: 127

mean_ms: 33.01

measuredAt: "2026-09-29T03:13:42.369Z"

p50_ms: 32

p95_ms: 33

particleCount: 12000

qualityTier: "medium"

render: {calls: 3, triangles: 28854, points: 12000, lines: 1989, programs: 3, …}

renderer: "Apple GPU"

rendererUnmasked: false

sceneState: "home"

screen: {width: 2048, height: 1280}

startupWorstFrame_ms: 114

tauriVersion: "2.11.5"

userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/60.5 Safari/605.1.15"

vendor: "Apple Inc."

viewport: {width: 1644, height: 610}

visibility: "visible"

webglVersion: "WebGL 2.0"

Object Prototype

__defineGetter__(propertyName, getterFunction)

__defineSetter__(propertyName, setterFunction)

__lookupGetter__(propertyName)

__lookupSetter__(propertyName)

constructor: function()

hasOwnProperty(propertyName)

isPrototypeOf(property)

propertyIsEnumerable(propertyName)

toLocaleString()

toString()

valueOf()
