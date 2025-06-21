<?php
/**
 * Plugin Name: Context Linker
 * Description: Рекомендует внутренние ссылки на основе JSON.
 * Version: 0.1.0
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
        echo '<div class="wrap"><h1>Context Linker</h1>';
        echo '<table class="widefat fixed" cellspacing="0">';
        echo '<thead><tr><th>Откуда ссылка</th><th>Анкор</th><th>Куда ссылка</th><th>Действие</th></tr></thead><tbody>';
        foreach ( $links as $index => $link ) {
            $apply_url = admin_url( 'admin-post.php?action=cl_apply&index=' . intval( $index ) );
            echo '<tr>';
            echo '<td>' . esc_html( $link['source_url'] ) . '</td>';
            echo '<td>' . esc_html( $link['anchor'] ) . '</td>';
            echo '<td>' . esc_html( $link['target_url'] ) . '</td>';
            echo '<td><a class="button" href="' . esc_url( $apply_url ) . '">Принять</a></td>';
            echo '</tr>';
        }
        echo '</tbody></table></div>';
    }

    public function handle_apply() {
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_die( 'Недостаточно прав.' );
        }
        $index = isset( $_GET['index'] ) ? intval( $_GET['index'] ) : -1;
        $links = $this->load_data();
        if ( isset( $links[ $index ] ) ) {
            $this->apply_link( $links[ $index ] );
        }
        wp_redirect( admin_url( 'admin.php?page=context-linker' ) );
        exit;
    }

    public function apply_link( $link ) {
        $source_post = $this->get_post_by_url( $link['source_url'] );
        if ( ! $source_post ) {
            return false;
        }
        $content = $source_post->post_content;
        $updated = $this->insert_link( $content, $link['anchor'], $link['target_url'] );
        if ( $updated !== $content ) {
            wp_update_post( array(
                'ID' => $source_post->ID,
                'post_content' => $updated,
            ) );
            return true;
        }
        return false;
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
