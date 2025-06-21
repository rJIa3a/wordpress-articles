<?php
if ( ! function_exists( 'esc_url' ) ) {
    function esc_url( $url ) {
        return filter_var( $url, FILTER_SANITIZE_URL );
    }
}

if ( ! function_exists( 'esc_html' ) ) {
    function esc_html( $text ) {
        return htmlspecialchars( $text, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8' );
    }
}
function cl_load_data( $file ) {
    if ( ! file_exists( $file ) ) {
        return array();
    }
    $json = file_get_contents( $file );
    $data = json_decode( $json, true );
    return is_array( $data ) ? $data : array();
}

function cl_insert_link( $content, $anchor, $url ) {
    $pattern = '/' . preg_quote( $anchor, '/' ) . '/u';
    $replacement = '<a href="' . esc_url( $url ) . '">' . esc_html( $anchor ) . '</a>';
    return preg_replace( $pattern, $replacement, $content, 1 );
}
