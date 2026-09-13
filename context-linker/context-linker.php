<?php
/**
 * Plugin Name: Context Linker
 * Description: Рекомендует внутренние ссылки на основе JSON.
 * Version: 0.2.0
 * Author: Example
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit; // Exit if accessed directly.
}

require_once __DIR__ . '/includes/linker-utils.php';

class Context_Linker {
    private $data_file;

    public function __construct( $file ) {
        $this->data_file = $file;
        add_action( 'admin_menu', array( $this, 'register_menu' ) );
        add_action( 'admin_post_cl_apply', array( $this, 'handle_apply' ) );
    }

    public function register_menu() {
        add_menu_page(
            'Context Linker',
            'Context Linker',
            'manage_options',
            'context-linker',
            array( $this, 'render_page' ),
            'dashicons-admin-links'
        );
    }

    public function load_data() {
        return cl_load_data( $this->data_file );
    }

    public function render_page() {
        if ( ! current_user_can( 'manage_options' ) ) {
            return;
        }
        $links = $this->load_data();
        echo '<div class="wrap"><h1>Context Linker</h1><p>Read-only: проверяйте предложения в локальном Universal Interlinker. Публикация отключена до реализации changeset и rollback.</p>';
        echo '<table class="widefat fixed" cellspacing="0">';
        echo '<thead><tr><th>Откуда ссылка</th><th>Анкор</th><th>Куда ссылка</th><th>Действие</th></tr></thead><tbody>';
        foreach ( $links as $index => $link ) {
            $apply_url = admin_url( 'admin-post.php?action=cl_apply&index=' . intval( $index ) );
            echo '<tr>';
            echo '<td>' . esc_html( $link['source_url'] ) . '</td>';
            echo '<td>' . esc_html( $link['anchor'] ) . '</td>';
            echo '<td>' . esc_html( $link['target_url'] ) . '</td>';
            echo '<td>Только просмотр</td>';
            echo '</tr>';
        }
        echo '</tbody></table></div>';
    }

    public function handle_apply() {
        wp_die( 'Read-only: запись в WordPress отключена.', 'Context Linker', array( 'response' => 403 ) );
    }

    public function apply_link( $link ) {
        return false; // No live writes before reviewed changesets and rollback exist.
    }

    public function get_post_by_url( $url ) {
        global $wpdb;
        $post_id = $wpdb->get_var( $wpdb->prepare( "SELECT ID FROM {$wpdb->posts} WHERE guid=%s", $url ) );
        if ( $post_id ) {
            return get_post( $post_id );
        }
        return null;
    }

    public function insert_link( $content, $anchor, $url ) {
        return cl_insert_link( $content, $anchor, $url );
    }
}

new Context_Linker( plugin_dir_path( __FILE__ ) . 'context_links.json' );
